"""Generate single-file HTML digest with embedded images for browser viewing and Reddit posting."""

import html
import os
import textwrap
from datetime import datetime

from output import CATEGORY_ORDER, format_source

CATEGORIES_COLORS = {
    "Robotics": "#ef4444",
    "AGI and Timeline": "#f97316",
    "Benchmarks and Reasoning": "#eab308",
    "AI Agents": "#22c55e",
    "AI Companies": "#06b6d4",
    "Hardware and Infra": "#3b82f6",
    "Non-LLM Automation": "#8b5cf6",
    "Pharma and Medical AI": "#ec4899",
    "Bioscience and Life Extension": "#14b8a6",
    "Post-Work and Economics": "#f59e0b",
    "AI Benefits": "#10b981",
    "AI Memes and Culture": "#a855f7",
}


def _escape(text: str) -> str:
    return html.escape(text or "")


def _category_color(cat: str) -> str:
    return CATEGORIES_COLORS.get(cat, "#6b7280")


def _escape_js(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")


def render_html(stories: list[dict], images_dir: str = "") -> str:
    """Render full HTML page with story cards, images, and Reddit copy buttons."""
    now_str = datetime.now().strftime("%B %d, %Y")
    sorted_stories = sorted(stories, key=lambda x: x.get("score", 0), reverse=True)

    groups: dict[str, list[dict]] = {}
    for s in sorted_stories:
        cat = s.get("category") or "Other"
        groups.setdefault(cat, []).append(s)
    for cat in groups:
        groups[cat].sort(key=lambda x: x.get("score", 0), reverse=True)

    all_cats = []
    for cat in CATEGORY_ORDER:
        if cat in groups:
            all_cats.append(cat)
    for cat in sorted(groups):
        if cat not in CATEGORY_ORDER:
            all_cats.append(cat)

    cards_html = ""
    copy_handlers = []

    for cat_idx, cat in enumerate(all_cats):
        items = groups[cat]
        color = _category_color(cat)

        cards_html += f'<h2 class="cat" style="border-left-color:{color}">{_escape(cat)}</h2>\n'

        for st_idx, s in enumerate(items):
            card_id = f"card{cat_idx}_{st_idx}"
            hook = _escape(s.get("hook") or s.get("title", "Untitled"))
            summary = _escape(s.get("summary") or "")
            takeaway = _escape(s.get("key_takeaway") or "")
            source = _escape(format_source(s))
            url = _escape(s.get("url", "#"))
            img_path = s.get("image_path", "")
            img_rel = f"images/{os.path.basename(images_dir)}/{os.path.basename(img_path)}" if img_path else ""

            reddit_text = f"{hook}\n\n{summary}\n\n{takeaway}" if takeaway else f"{hook}\n\n{summary}"
            reddit_escaped = _escape_js(reddit_text)
            handler = f"function copy{cat_idx}{st_idx}(){{navigator.clipboard.writeText('{reddit_escaped}');document.getElementById('btn{cat_idx}{st_idx}').textContent='Copied!';setTimeout(()=>{{document.getElementById('btn{cat_idx}{st_idx}').textContent='Copy for Reddit'}},1500);}}"
            copy_handlers.append(handler)

            img_section = ""
            if img_rel:
                img_section = f'<div class="img-wrap"><a href="{url}" target="_blank"><img src="{img_rel}" loading="lazy" alt=""></a></div>\n'

            cards_html += f"""
        <div class="card" id="{card_id}">
          {img_section}
          <div class="card-body">
            <h3><a href="{url}" target="_blank">{hook}</a></h3>
            <p class="summary">{summary}</p>
            {'<p class="takeaway">' + takeaway + '</p>' if takeaway else ""}
            <div class="card-footer">
              <span class="source">{source}</span>
              <div class="actions">
                <a href="{url}" target="_blank" class="btn">Source</a>
                <button id="btn{cat_idx}{st_idx}" class="btn-copy" onclick="copy{cat_idx}{st_idx}()">Copy for Reddit</button>
              </div>
            </div>
          </div>
        </div>\n"""

    handlers_js = "\n".join(f"  {h}" for h in copy_handlers)

    full = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Horizon News - {now_str}</title>
<style>
  :root {{
    --bg: #0f1117;
    --card-bg: #1a1b26;
    --text: #e5e7eb;
    --muted: #9ca3af;
    --accent: #6ee7b7;
    --link: #7dd3fc;
    --border: #2d2f3a;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.6;
    max-width: 900px;
    margin: 0 auto;
    padding: 2rem 1.5rem;
  }}
  h1 {{
    font-size: 2rem;
    color: var(--accent);
    margin-bottom: 0.25rem;
  }}
  .subtitle {{
    color: var(--muted);
    margin-bottom: 2rem;
    font-size: 1.05rem;
  }}
  .cat {{
    font-size: 1.25rem;
    border-left: 4px solid #666;
    padding-left: 0.75rem;
    margin: 2rem 0 1rem;
  }}
  .cat:first-of-type {{ margin-top: 1rem; }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 1rem;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }}
  .img-wrap {{
    width: 100%;
    max-height: 360px;
    overflow: hidden;
    display: flex;
  }}
  .img-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
  .card-body {{ padding: 1.25rem; }}
  .card-body h3 {{
    font-size: 1.1rem;
    line-height: 1.35;
    margin-bottom: 0.6rem;
  }}
  .card-body h3 a {{
    color: var(--text);
    text-decoration: none;
  }}
  .card-body h3 a:hover {{ color: var(--link); }}
  .summary {{
    font-size: 0.95rem;
    color: var(--muted);
    margin-bottom: 0.5rem;
  }}
  .takeaway {{
    font-size: 0.9rem;
    color: var(--accent);
    font-style: italic;
    margin-bottom: 0.6rem;
  }}
  .card-footer {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid var(--border);
    padding-top: 0.75rem;
    margin-top: 0.5rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }}
  .source {{
    font-size: 0.82rem;
    color: var(--muted);
  }}
  .actions {{ display: flex; gap: 0.5rem; }}
  .btn, .btn-copy {{
    font-size: 0.82rem;
    padding: 0.35rem 0.85rem;
    border-radius: 6px;
    border: 1px solid var(--border);
    cursor: pointer;
    text-decoration: none;
    font-weight: 500;
    transition: background 0.15s;
  }}
  .btn {{
    background: transparent;
    color: var(--link);
  }}
  .btn:hover {{ background: rgba(125,211,252,0.1); }}
  .btn-copy {{
    background: transparent;
    color: var(--muted);
  }}
  .btn-copy:hover {{ background: rgba(110,231,183,0.1); color: var(--accent); }}
  footer {{
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    color: var(--muted);
    font-size: 0.85rem;
    text-align: center;
  }}
  @media (max-width: 600px) {{
    body {{ padding: 1rem; }}
    h1 {{ font-size: 1.5rem; }}
    .card-footer {{ flex-direction: column; align-items: flex-start; }}
    .actions {{ width: 100%; justify-content: flex-start; }}
  }}
</style>
</head>
<body>
<h1>The Horizon News</h1>
<p class="subtitle">{now_str} | {len(stories)} stories</p>

{cards_html}

<footer>The Horizon News - curated daily</footer>

<script>
{handlers_js}
</script>
</body>
</html>"""
    return full


def save_html(full_html: str, output_dir: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{today}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(full_html)
    return path

def render_index(reports_dir: str) -> str:
    """Render a simple index.html listing all available reports."""
    now_str = datetime.now().strftime("%B %d, %Y")
    
    # Find all .html files in the reports directory
    files = []
    if os.path.isdir(reports_dir):
        for f in os.listdir(reports_dir):
            if f.endswith(".html") and f != "index.html":
                files.append(f)
    
    # Sort files descending (newest first)
    files.sort(reverse=True)
    
    links_html = ""
    for f in files:
        date = f.replace(".html", "")
        links_html += f'<li><a href="reports/{f}">{date}</a></li>\n'
    
    full = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Horizon News Archive</title>
<style>
  :root {{
    --bg: #0f1117;
    --text: #e5e7eb;
    --accent: #6ee7b7;
    --link: #7dd3fc;
    --border: #2d2f3a;
  }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 600px;
    margin: 4rem auto;
    padding: 0 1.5rem;
    text-align: center;
  }}
  h1 {{
    font-size: 2rem;
    color: var(--accent);
    margin-bottom: 2rem;
  }}
  ul {{ list-style: none; padding: 0; }}
  li {{ margin: 1rem 0; }}
  a {{ 
    color: var(--link); 
    text-decoration: none; 
    font-size: 1.2rem; 
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    display: inline-block;
    transition: background 0.2s;
  }}
  a:hover {{ background: rgba(125,211,252,0.1); }}
</style>
</head>
<body>
  <h1>The Horizon News Archive</h1>
  <p style="margin-bottom: 2rem; color: #9ca3af;">Select a date to view the digest</p>
  <ul>
    {links_html}
  </ul>
</body>
</html>"""
    return full

def save_index(index_html: str, output_dir: str) -> str:
    """Saves the index.html to the root of the output directory."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(index_html)
    return path

