import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)

def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))

def _env_float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))

def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # LLM (Provider 1 - main)
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", ""))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", "not-needed"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", ""))
    temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.7))
    max_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_TOKENS", 8192))

    # VLM (for image/meme analysis)
    vlm_model: str = field(default_factory=lambda: _env("VLM_MODEL", "gemma-4-26b-a4b-it"))

    # SearXNG
    searxng_url: str = field(default_factory=lambda: _env("SEARXNG_URL", ""))

    # Schedule
    schedule_timezone: str = field(default_factory=lambda: _env("SCHEDULE_TIMEZONE", "America/New_York"))
    schedule_hour: int = field(default_factory=lambda: _env_int("SCHEDULE_HOUR", 6))
    schedule_minute: int = field(default_factory=lambda: _env_int("SCHEDULE_MINUTE", 0))

    # News params
    max_stories: int = field(default_factory=lambda: _env_int("NEWS_MAX_STORIES", 30))
    stories_per_category: int = field(default_factory=lambda: _env_int("NEWS_STORIES_PER_CATEGORY", 3))
    dedup_days: int = field(default_factory=lambda: _env_int("NEWS_DEDUP_DAYS", 7))
    summarize_concurrency: int = field(default_factory=lambda: _env_int("NEWS_SUMMARIZE_CONCURRENCY", 3))
    time_range: str = field(default_factory=lambda: _env("NEWS_TIME_RANGE", "month"))


    # Output
    output_dir: str = field(default_factory=lambda: _env("NEWS_OUTPUT_DIR", ""))
    data_dir: str = field(default_factory=lambda: _env("NEWS_DATA_DIR", "./data"))


defaults = Settings()
