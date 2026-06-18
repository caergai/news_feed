"""Generate daily markdown digest from curated stories."""
import os
from datetime import datetime


CATEGORY_ORDER = [
    "Robotics",
    "AGI and Timeline",
    "Futurism",
    "Philosophy",
    "Politics of Labor",
    "Benchmarks and Reasoning",
    "AI Agents",
    "AI Companies",
    "Hardware and Infra",
    "Non-LLM Automation",
    "Pharma and Medical AI",
    "Bioscience and Life Extension",
    "Post-Work and Economics",
    "AI Anxiety",
    "AI Myth vs. Fact",
    "AI Benefits",
    "AI Memes and Culture",
]


def format_source(s: dict) -> str:
    parts = []
    platform = (s.get("source_platform") or "").lower()
    if platform == "twitter":
        parts.append("Twitter/X")
    elif platform == "reddit":
        parts.append("Reddit")
    elif platform == "image":
        parts.append("Image")
    src = s.get("engine", "").title()
    if src and src not in parts:
        parts.append(src)
    if not parts:
        parts.append("News")
    return " via " + parts[0]


def format_story(s: dict, rank: int) -> str:
    lines = []
    hook = (s.get("hook") or "").strip()
    summary = (s.get("summary") or "").strip()
    takeaway = (s.get("key_takeaway") or "").strip()
    snippet = (s.get("snippet") or "").strip()

    lines.append(f"{rank}. **{hook or s.get('title', 'Untitled')}**")
    lines.append("")

    if summary:
        lines.append(summary)
    elif hook and not takeaway:
        lines.append(f"*{hook}*")

    if takeaway:
        lines.append("")
        lines.append(f"*Takeaway: {takeaway}*")

    # Fallback when LLM didn't produce summary or hook
    if not summary and not hook and snippet:
        lines.append(snippet)

    lines.append("")
    short_url = s.get("url", "").split("://")[-1][:70]
    lines.append(f"*Link: [{short_url}]({s['url']}){format_source(s)}*")
    lines.append("")
    return "\n".join(lines)


def render_digest(stories: list[dict]) -> str:
    now_str = datetime.now().strftime("%B %d, %Y")
    sorted_stories = sorted(stories, key=lambda x: x.get("score", 0), reverse=True)

    groups: dict[str, list[dict]] = {}
    for s in sorted_stories:
        cat = s.get("category") or "Other"
        groups.setdefault(cat, []).append(s)
    for cat in groups:
        groups[cat].sort(key=lambda x: x.get("score", 0), reverse=True)

    lines = [
        f"# The Horizon Daily News",
        " ",
        f"**{now_str}** | {len(stories)} stories",
        " ",
    ]

    for cat in CATEGORY_ORDER:
        if cat not in groups:
            continue
        items = groups[cat]
        lines.append(f"## {cat}")
        lines.append("")
        for i, s in enumerate(items, 1):
            lines.append(format_story(s, i))

    leftovers = {k: v for k, v in groups.items() if k not in CATEGORY_ORDER}
    for cat in sorted(leftovers):
        lines.append(f"## {cat}")
        lines.append("")
        for i, s in enumerate(leftovers[cat], 1):
            lines.append(format_story(s, i))

    lines.extend([
        "---",
        "",
        f"*The Horizon News - curated daily at 6 AM ET*",
        "",
    ])
    return "\n".join(lines)


def save_digest(digest: str, output_dir: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{today}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(digest)
    return path


def save_feed_json(stories: list[dict], output_dir: str, max_items: int = 3) -> str:
    """Save a small JSON feed compatible with VRChat VRCStringDownloader + SimpleJsonParser."""
    import json as _json
    sorted_stories = sorted(stories, key=lambda x: x.get("score", 0), reverse=True)[:max_items]
    children = []
    for s in sorted_stories:
        title = (s.get("hook") or s.get("title", "Untitled")).strip()
        body = (s.get("summary") or s.get("snippet", "")).strip()
        if len(body) > 200:
            body = body[:197] + "..."
        children.append({"kind": "t3", "data": {"title": title, "selftext": body}})
    feed = {"data": {"children": children}}
    index_dir = os.path.dirname(output_dir)
    path = os.path.join(index_dir, "feed.json")
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(feed, f, indent=2, ensure_ascii=False)
    return path
