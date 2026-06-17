import asyncio
import hashlib
import logging
import os
import sqlite3
import threading
import time

log = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_conn_dir: str | None = None


def _get_conn(data_dir: str) -> sqlite3.Connection:
    global _conn, _conn_dir
    if _conn is not None and _conn_dir == data_dir:
        return _conn
    os.makedirs(data_dir, exist_ok=True)
    conn = sqlite3.connect(os.path.join(data_dir, "fetch_cache.db"), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS fetch_cache ("
        "  url_hash TEXT PRIMARY KEY, url TEXT, text TEXT, fetched_at REAL)"
    )
    conn.commit()
    _conn, _conn_dir = conn, data_dir
    return conn


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def get(url: str, data_dir: str, ttl_hours: float) -> str | None:
    if ttl_hours <= 0:
        return None
    try:
        with _lock:
            conn = _get_conn(data_dir)
            row = conn.execute(
                "SELECT text, fetched_at FROM fetch_cache WHERE url_hash = ?",
                (_hash(url),),
            ).fetchone()
        if row is None:
            return None
        text, fetched_at = row
        if time.time() - fetched_at > ttl_hours * 3600:
            return None
        return text or None
    except Exception as e:
        log.warning("cache.get failed: %s", e)
        return None


def put(url: str, text: str, data_dir: str) -> None:
    if not text:
        return
    try:
        with _lock:
            conn = _get_conn(data_dir)
            conn.execute(
                "INSERT OR REPLACE INTO fetch_cache (url_hash, url, text, fetched_at) VALUES (?,?,?,?)",
                (_hash(url), url, text, time.time()),
            )
            conn.commit()
    except Exception as e:
        log.warning("cache.put failed: %s", e)
