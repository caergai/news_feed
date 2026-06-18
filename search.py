"""Search via SearXNG with Twitter/X and image support."""
import asyncio
import logging
import time
import httpx
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from config import Settings
import event_log

log = logging.getLogger(__name__)

_TRACKING = {"fbclid", "gclid", "msclkid", "igshid", "ref", "utm_source"}

CATEGORIES = {
    "Politics": ["major political shifts 2026", "geopolitical tensions news", "diplomatic breakthroughs 2026"],
    "Technology": ["cutting edge technology news 2026", "digital transformation breakthroughs", "tech innovation 2026"],
    "Science": ["scientific discovery 2026", "space exploration news", "fundamental research breakthroughs"],
    "Culture & Arts": ["cultural trends 2026", "significant artistic achievements", "societal shifts news"],
    "Economics & Finance": ["global economic trends 2026", "market disruptions news", "global financial news 2026"],
    "Health & Medicine": ["medical breakthrough 2026", "public health updates news", "health research breakthroughs"],
    "Environment & Climate": ["climate solutions 2026", "ecological discoveries news", "environmental challenges solutions"],
    "Global Affairs": ["international conflict news", "united nations reports 2026", "global affairs analysis"],
    "Sports": ["major sports news 2026", "olympics updates", "world cup news"],
    "Human Interest": ["inspiring human interest stories 2026", "human resilience stories", "ingenuity stories news"],
    "Twitter Global": ["site:x.com world news", "site:x.com breaking news", "site:twitter.com global trends"],
    "Twitter Culture": ["site:x.com current events meme", "site:x.com world news funny"],
}


def _canonicalize(url: str) -> str:
    try:
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return url
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if k.lower() not in _TRACKING and not k.lower().startswith("utm_")]
        path = parts.path.rstrip("/") if parts.path != "/" else parts.path
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))
    except Exception:
        return url


async def search_one(query: str, settings: Settings) -> list[dict]:
    """Search one query. Returns list of {url, title, snippet, engine}."""
    url = f"{settings.searxng_url.rstrip('/')}/search"
    params = {"q": query, "format": "json", "time_range": settings.time_range}
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for r in data.get("results", []):
            results.append({
                "url": _canonicalize(r.get("url", "")),
                "title": r.get("title", ""),
                "snippet": r.get("content", "")[:300],
                "engine": r.get("engine", "unknown"),
                "score": r.get("score", 0),
            })
        event_log.log_event("search", {"query": query, "results": len(results)})
        return results
    except Exception as e:
        log.error("Search failed for '%s': %s", query, e)
        return []


async def search_images(query: str, settings: Settings) -> list[dict]:
    """Search for images. Returns list with img_src."""
    url = f"{settings.searxng_url.rstrip('/')}/search"
    params = {"q": query, "format": "json", "categories": "images", "time_range": settings.time_range}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for r in data.get("results", []):
            results.append({
                "url": _canonicalize(r.get("url", "")),
                "title": r.get("title", ""),
                "snippet": r.get("content", "")[:300],
                "engine": r.get("engine", "image"),
                "img_src": r.get("img_src", ""),
            })
        return results
    except Exception as e:
        log.error("Image search failed for '%s': %s", query, e)
        return []


async def search_all(settings: Settings) -> list[dict]:
    """Fan out all category queries, deduplicate, return candidates."""
    all_raw: list[dict] = []

    # Text searches for all categories
    tasks = []
    for cat, queries in CATEGORIES.items():
        for q in queries:
            tasks.append(search_one(q, settings))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_raw.extend(r)

    # Deduplicate by canonical URL
    seen: dict[str, dict] = {}
    for item in all_raw:
        key = item["url"]
        if not key or key in seen:
            continue
        # Prefer items with images for meme queries
        if key in seen and item.get("img_src") and not seen[key].get("img_src"):
            seen[key] = item
        else:
            seen[key] = item

    candidates = list(seen.values())
    event_log.log_event("search_complete", {"total_candidates": len(candidates)})
    return candidates
