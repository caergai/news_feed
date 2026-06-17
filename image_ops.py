"""Image download and og:image extraction helpers."""

import asyncio
import logging
import os
import re
from mimetypes import guess_extension

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"


def _sanitize_filename(slug: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower())
    return slug.strip("-")[:60]


def _get_image_ext(url: str, content_type: str = "") -> str:
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    for ext in ALLOWED_EXTS:
        if path.endswith(ext):
            return ext
    if content_type:
        ext = guess_extension(content_type)
        if ext and ext in ALLOWED_EXTS:
            return ext
    return ".jpg"


async def extract_og_image(url: str, timeout: int = 8) -> str | None:
    """Fetch a webpage and return og:image URL, or None."""
    headers = {"User-Agent": UA}
    try:
        # Strip fragment and query beyond reasonable bounds
        clean_url = url.split("#")[0]
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(clean_url, headers=headers)
            if resp.status_code not in (200, 404) or len(resp.text) < 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            tag = soup.find("meta", attrs={"property": "og:image"})
            if tag and tag.get("content"):
                img = tag["content"].strip()
                return _resolve_url(img, url)
    except Exception as e:
        log.debug("og:image extract failed for %s: %s", url, e)
    return None


def _resolve_url(img: str, base_url: str) -> str:
    from urllib.parse import urljoin
    if img.startswith("//"):
        return "https:" + img
    elif img.startswith("http"):
        return img
    return urljoin(base_url, img)


async def download_image(url: str, dest_dir: str, filename: str, timeout: int = 15) -> str | None:
    """Download an image to dest_dir/filename. Returns local path or None."""
    os.makedirs(dest_dir, exist_ok=True)
    base_name = filename.rsplit(".", 1)[0]

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": UA})
            if resp.status_code != 200:
                return None
            data = resp.content
            if len(data) > MAX_IMAGE_SIZE:
                return None
            if len(data) < 1024:
                return None
            content_type = resp.headers.get("content-type", "")
            if content_type.startswith("text/") and not content_type.startswith("text/css"):
                return None
            if "html" in content_type or "json" in content_type:
                return None
    except Exception as e:
        log.debug("Image download failed for %s: %s", url, e)
        return None

    ext = _get_image_ext(url, content_type)
    if not ext.startswith("."):
        ext = f".{ext}"
    final_name = f"{base_name}{ext}"
    dest_path = os.path.join(dest_dir, final_name)
    with open(dest_path, "wb") as f:
        f.write(data)
    return dest_path


async def get_image_for_story(story: dict, base_image_dir: str, index: int) -> str | None:
    """Get og:image first, then fallback to search thumbnail. Download and return local path or None."""
    story_url = story.get("url", "")
    thumb_url = story.get("image_url") or story.get("img_src", "")
    title = story.get("title", "untitled")
    slug = _sanitize_filename(title)
    filename = f"{index:02d}_{slug}"

    engine = (story.get("engine") or "").lower()
    is_img_search = engine in ("bing images", "google images", "yandex images", "duckduckgo images")

    og_url = None
    if not is_img_search and story_url:
        og_url = await extract_og_image(story_url)

    download_url = og_url or thumb_url
    if not download_url or not download_url.startswith("http"):
        return None

    result = await download_image(download_url, base_image_dir, filename, timeout=15)
    if result:
        log.info("Downloaded image for story %d: %s", index, os.path.basename(result))
    return result


async def download_images_parallel(stories: list[dict], base_image_dir: str, concurrency: int = 5) -> int:
    """Download images for all stories concurrently. Returns count of downloaded images."""
    sem = asyncio.Semaphore(concurrency)
    img_count = 0

    async def _dl(i: int, story: dict):
        nonlocal img_count
        async with sem:
            path = await get_image_for_story(story, base_image_dir, i)
            story["image_path"] = path or ""
            if path:
                img_count += 1

    tasks = [_dl(i, s) for i, s in enumerate(stories, 1)]
    await asyncio.gather(*tasks, return_exceptions=True)
    return img_count
