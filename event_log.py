"""Structured JSONL event log for the news bot."""
from __future__ import annotations
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

_write_lock = threading.Lock()
_LOG_DIR = None

def log_dir() -> Path:
    global _LOG_DIR
    if _LOG_DIR is None:
        from config import defaults
        _LOG_DIR = Path(defaults.data_dir) / "logs"
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR

def log_event(event: str, data: dict | None = None) -> None:
    ts = datetime.now().isoformat(timespec="milliseconds")
    entry = {"ts": ts, "event": event}
    if data:
        entry["data"] = data
    line = json.dumps(entry, ensure_ascii=False, default=str)
    daily = datetime.now().strftime("%Y-%m-%d")
    path = log_dir() / f"{daily}.jsonl"
    with _write_lock:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
