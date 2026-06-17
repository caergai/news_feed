import asyncio
import logging
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

load_dotenv()

import config
from llm import LLMClient
from search import search_all
import category_prompts as prompts
from output import save_digest, render_digest
from output_html import save_html, render_html as render_html_digest
from image_ops import download_images_parallel, get_image_for_story
import event_log
import git_ops

log = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_seen_db(data_dir: str) -> sqlite3.Connection:
    os.makedirs(data_dir, exist_ok=True)
    conn = sqlite3.connect(os.path.join(data_dir, "seen_urls.db"))
    conn.execute("CREATE TABLE IF NOT EXISTS seen_urls (url TEXT PRIMARY KEY, seen_at INTEGER)")
    conn.commit()
    return conn


def _guess_category(c: dict) -> str:
    """Quick keyword-based category guess for fallback when LLM curation fails."""
    t = f"{c.get('title', '')} {c.get('snippet', '')}".lower()
    u = c.get("url", "").lower()
    if any(w in t for w in ["election", "government", "policy", "senate", "parliament", "diplomacy", "treaty"]):
        return "Politics"
    if any(w in t for w in ["ai", "tech", "software", "hardware", "silicon", "computing", "gadget", "innovation"]):
        return "Technology"
    if any(w in t for w in ["discovery", "physics", "astronomy", "space", "biology", "research", "experiment"]):
        return "Science"
    if any(w in t for w in ["art", "music", "movie", "film", "literature", "exhibition", "fashion", "celebrity"]):
        return "Culture & Arts"
    if any(w in t for w in ["market", "stock", "economy", "finance", "trade", "inflation", "banking", "investment"]):
        return "Economics & Finance"
    if any(w in t for w in ["health", "medical", "virus", "cancer", "drug", "hospital", "wellness", "surgeon"]):
        return "Health & Medicine"
    if any(w in t for w in ["climate", "environment", "carbon", "nature", "wildlife", "ecology", "warming"]):
        return "Environment & Climate"
    if any(w in t for w in ["war", "conflict", "border", "international", "global", "un", "nato", "foreign"]):
        return "Global Affairs"
    if any(w in t for w in ["sports", "olympics", "football", "basketball", "tennis", "athlete", "match"]):
        return "Sports"
    return "Human Interest"  # generic catch-all


def _guess_platform(c: dict) -> str:
    u = c.get("url", "").lower()
    if "x.com" in u or "twitter.com" in u:
        return "twitter"
    if "reddit.com" in u or "redd.it" in u:
        return "reddit"
    engine = (c.get("engine") or "").lower()
    if engine in ("bing images", "google images", "yandex images", "duckduckgo images"):
        return "image"
    return "news"


def _mark_seen(db: sqlite3.Connection, url: str) -> None:
    ts = int(time.time())
    db.execute("INSERT OR REPLACE INTO seen_urls (url, seen_at) VALUES (?, ?)", (url, ts))
    db.commit()


def _load_historical_digests(output_dir: str) -> set[str]:
    """Scan all previous .md digest files and extract URLs."""
    urls: set[str] = set()
    if not os.path.isdir(output_dir):
        return urls
    pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
    for fname in os.listdir(output_dir):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(output_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    for match in pattern.finditer(line):
                        urls.add(match.group(2))
        except Exception:
            pass
    return urls


def _merge_seen(source_db: sqlite3.Connection, source_dedup_days: int,
                source_output_dir: str) -> set[str]:
    """Merge DB dedup window + historical digest URLs into one set."""
    combined: set[str] = set()
    cutoff = int(time.time()) - source_dedup_days * 86400
    for row in source_db.execute(
        "SELECT url FROM seen_urls WHERE seen_at >= ?", (cutoff,)
    ).fetchall():
        combined.add(row[0])
    combined.update(_load_historical_digests(source_output_dir))
    return combined


async def run_curation(llm: LLMClient, candidates: list[dict], seen: set[str], max_stories: int = 30) -> list[dict]:
    """LLM curates the best stories from all candidates."""
    fresh = [c for c in candidates if c["url"] not in seen and len(c["url"]) > 10]
    if not fresh:
        log.info("No fresh candidates after dedup")
        return []

    # Sort by search score and take top 100 to prevent LLM context overflow/timeouts
    fresh.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_candidates = fresh[:100]

    blocks = []
    for i, c in enumerate(top_candidates, 1):
        parts = [f"{i}. **{c['title']}**", f"   URL: {c['url']}"]
        if c.get("snippet"):
            parts.append(f"   Snippet: {c['snippet']}")
        if c.get("img_src"):
            parts.append(f"   Image: {c['img_src']}")
        parts.append(f"   Engine: {c['engine']}")
        blocks.append("\n".join(parts))

    user_msg = f"You have {len(top_candidates)} high-quality candidates. Select the best ~{max_stories}.\n\n" + "\n\n".join(blocks)
    try:
        prompt = prompts.CURATE_PROMPT.format(max_stories=max_stories)
        result = await llm.achat_json(prompt, user_msg, retries=2, max_tokens=16000)
        selected = result.get("selected", [])
        # Dedup within LLM selection
        seen_urls: set[str] = set()
        deduped: list[dict] = []
        for s in selected:
            url = s.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                deduped.append(s)
        selected = deduped
        log.info("Curation selected %d from %d candidates", len(selected), len(top_candidates))
        event_log.log_event("curation", {"selected": len(selected), "from": len(top_candidates)})
        return selected
    except Exception as e:
        log.warning("Curation LLM failed (%s), using keyword fallback", e)
        seen_urls: set[str] = set()
        fallback = []
        for c in sorted(fresh, key=lambda x: x.get("score", 0), reverse=True):
            if c["url"] not in seen_urls and len(fallback) < max_stories:
                seen_urls.add(c["url"])
                fallback.append({
                    **c, "category": _guess_category(c),
                    "score": c.get("score", 5),
                    "source_platform": _guess_platform(c),
                    "has_image": bool(c.get("img_src")),
                    "image_url": c.get("img_src"),
                })
        return fallback


async def run_summarization(llm: LLMClient, selected: list[dict], concurrency: int = 3) -> list[dict]:
    """Summarize selected stories. Images go through VLM, text through LLM."""
    sem = asyncio.Semaphore(concurrency)

    async def summarize_text(story: dict):
        async with sem:
            user_msg = (
                f"Title: {story['title']}\n"
                f"URL: {story['url']}\n"
                f"Snippet: {story.get('snippet', '')}"
            )
            try:
                r = await llm.achat_json(prompts.SUMMARIZE_TEXT_PROMPT, user_msg, retries=1)
                story["hook"] = r.get("hook", "")
                story["summary"] = r.get("summary", "")
                story["key_takeaway"] = r.get("key_takeaway", "")
            except Exception as e:
                log.warning("Summary failed for '%s': %s", story["title"][:40], e)
                story["hook"] = ""
                story["summary"] = (story.get("snippet") or f"Story about: {story['title']}")
                story["key_takeaway"] = ""
        return story

    async def summarize_image(story: dict):
        img_url = story.get("image_url") or story.get("img_src", "")
        async with sem:
            user_text = (
                f"Source page title: {story['title']}\n"
                f"Source URL: {story['url']}\n"
                f"Snippet/context: {story.get('snippet', '')}"
            )
            try:
                r = await llm.avision_json(prompts.VISION_ANALYZE_PROMPT, img_url, user_text, retries=1)
                story["hook"] = r.get("hook", story["title"])
                story["summary"] = r.get("summary", f"[Image content] {story['title']}")
            except Exception as e:
                log.warning("VLM failed for image '%s': %s", img_url[:60], e)
                story["hook"] = story["title"]
                story["summary"] = f"[Image content] {story['title']}"
        return story

    tasks = []
    for story in selected:
        img_url = story.get("image_url") or story.get("img_src", "")
        engine = (story.get("engine") or "").lower()
        is_img_search = engine in ("bing images", "google images", "yandex images", "duckduckgo images")
        is_img_story = story.get("source_platform") == "image" or is_img_search
        if img_url and is_img_story:
            story["has_image"] = True
            tasks.append(summarize_image(story))
        else:
            tasks.append(summarize_text(story))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    summarized = [r for r in results if isinstance(r, dict)]
    for r in results:
        if isinstance(r, Exception):
            log.error("Summarization task failed: %s", r)

    event_log.log_event("summarization", {"count": len(summarized)})
    return summarized


async def run_news(settings: config.Settings | None = None) -> str | None:
    """Execute the full daily news pipeline. Returns output path or None."""
    s = settings or config.defaults
    out_dir = s.output_dir or _DEFAULT_OUTPUT_DIR

    start = time.time()
    sid = str(uuid.uuid4())[:8]
    log.info("[%s] Starting daily news run", sid)
    event_log.log_event("pipeline_start", {"sid": sid})

    # Dedup
    db = _get_seen_db(s.data_dir)
    seen = _merge_seen(db, s.dedup_days, out_dir)
    log.info("[%s] Total %d URLs in dedup (DB + historical digests)", sid, len(seen))

    # Phase 1: Search
    llm = LLMClient(s)
    candidates = await search_all(s)
    log.info("[%s] Got %d raw candidates", sid, len(candidates))
    if not candidates:
        log.error("[%s] No candidates found", sid)
        return None

    # Phase 2: Curation
    selected = await run_curation(llm, candidates, seen, max_stories=s.max_stories)
    if not selected:
        log.error("[%s] No stories after curation", sid)
        return None

    # Phase 3: Summarization
    summarized = await run_summarization(llm, selected, concurrency=s.summarize_concurrency)

    # Phase 3.5: Download images
    today_str = datetime.now().strftime("%Y-%m-%d")
    base_image_dir = os.path.join(out_dir, "images", today_str)
    log.info("[%s] Downloading images for %d stories", sid, len(summarized))

    img_count = await download_images_parallel(summarized, base_image_dir, concurrency=5)
    log.info("[%s] Downloaded %d images", sid, img_count)

    # Phase 4: Output
    digest = render_digest(summarized)
    path = save_digest(digest, out_dir)

    # HTML output
    html_content = render_html_digest(summarized, base_image_dir)
    html_path = save_html(html_content, out_dir)
    log.info("[%s] HTML written to %s", sid, html_path)

    # Index page output
    from output_html import render_index, save_index
    # Note: reports are actually in out_dir/reports since we moved them
    idx_content = render_index(os.path.join(out_dir, "reports"))
    idx_path = save_index(idx_content, out_dir)
    log.info("[%s] Index written to %s", sid, idx_path)

    elapsed = time.time() - start

    log.info("[%s] Done in %.0fs. %d stories -> %s (HTML: %s)", sid, elapsed, len(summarized), path, html_path)
    event_log.log_event("pipeline_end", {
        "sid": sid, "elapsed": round(elapsed, 1),
        "candidates": len(candidates), "selected": len(selected),
        "summarized": len(summarized), "images": img_count,
        "path": path, "html_path": html_path,
    })

    # Push to GitHub
    git_ops.push_reports()

    return path


def _scheduled_run():
    """Sync job target for BlockingScheduler — runs async pipeline in new loop."""
    asyncio.run(run_news())


def run_daemon():
    """Run with BlockingScheduler (daily at configured time)."""
    s = config.defaults
    sched = BlockingScheduler(timezone=s.schedule_timezone)
    sched.add_job(
        _scheduled_run, "cron",
        hour=s.schedule_hour, minute=s.schedule_minute,
        id="daily_news", replace_existing=True, misfire_grace_time=7200,
    )
    logging.info("Scheduler started: daily at %02d:%02d %s (press Ctrl+C to stop)",
                 s.schedule_hour, s.schedule_minute, s.schedule_timezone)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()


def entrypoint():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    mode = sys.argv[1] if len(sys.argv) > 1 else "run"

    if mode == "daemon":
        run_daemon()
    else:
        path = asyncio.run(run_news())
        if path:
            date_str = datetime.now().strftime("%Y-%m-%d")
            html_path = path.replace(".md", ".html")
            images_dir = os.path.join(os.path.dirname(path), "images", date_str)
            print(f"Digest written to: {path}")
            print(f"HTML written to:  {html_path}")
            print(f"Images folder:    {images_dir}")
            # Show image count
            if os.path.exists(images_dir):
                img_count = len([f for f in os.listdir(images_dir) if f.endswith((".jpg", ".png", ".gif", ".webp"))])
                print(f"Images downloaded: {img_count}")
            
            # Open result in browser
            try:
                os.system(f'open "{html_path}"')
            except Exception as e:
                print(f"Could not open browser: {e}")
        else:
            print("Pipeline completed but no output generated.")


if __name__ == "__main__":
    entrypoint()
