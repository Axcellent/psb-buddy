from __future__ import annotations

import os
import math
from pathlib import Path


def env(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    return default if not value or value == name else value


def env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(float(env(name)))))
    except (ValueError, OverflowError):
        return default


def env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(env(name))
        return max(low, min(high, value)) if math.isfinite(value) else default
    except ValueError:
        return default


DATA_DIR = Path(env("DATA_DIR", "data"))

API_BASE = (env("LLM_BASE_URL") or env("OPENAI_BASE_URL") or env("BASE_URL")).rstrip("/")
API_KEY = env("LLM_API_KEY") or env("OPENAI_API_KEY")
EMBED_KEY = env("EMBEDDER_API_KEY") or API_KEY
RERANK_KEY = env("RERANKER_API_KEY") or API_KEY

LLM_MODEL = (
    env("LLM_MODEL") or env("OPENAI_MODEL") or env("GEN_MODEL") or "deepseek/deepseek-v4.1-flash"
)
EMB_MODEL = env("EMB_MODEL", "baai/bge-m3")
RERANKER_MODEL = env("RERANKER_MODEL", "qwen3-reranker-8b")
USE_RERANKER = env("USE_RERANKER", "0").lower() in ("1", "true", "yes")
RERANK_CANDIDATES = env_int("RERANK_CANDIDATES", 12, 2, 50)
RERANK_DOC_CHARS = 1500

TEMPERATURE = env_float("TEMPERATURE", 0.0, 0.0, 2.0)
MAX_TOKENS = env_int("MAX_TOKENS", 1024, 256, 8192)
MAX_WORKERS = env_int("MAX_WORKERS", 4, 1, 8)
SELF_CHECK = env("SELF_CHECK", "1").lower() in ("1", "true", "yes")
MIN_ANSWER_TOKENS = 4096
ANSWER_TEMPERATURE = 0.0

TIME_BUDGET_SECONDS = 15 * 60
HARD_DEADLINE_SECONDS = 17.5 * 60
REQUEST_TIMEOUT_SECONDS = 75.0
HINT_CANDIDATES = 30
HINT_LIMIT = 6
HINT_PER_DOCUMENT = 2
HINT_MIN_RATIO = 0.5
EDITION_DOCUMENTS = 2
COMPACT_COMPANY_DOCUMENTS = 3
COMPACT_LAW_CHUNKS = 6
COMPACT_HINTS = 4
RECHECK_CLOSEST = 8
RECHECK_LIMIT = 18
HINT_CHARS = 320
SMALL_ARTICLE_CHARS = 12_000
MAX_FULL_ARTICLES = 2

COMPANY_FULLTEXT_LIMIT = 60_000
LAW_CONTEXT_CHARS = 12_000
LAW_TOP_CHUNKS = 10

MAX_ANSWER_CHARS = 9_500
FALLBACK_ANSWER = (
    "Не удалось сформировать ответ по базе знаний из-за технической ошибки. "
    "Повторите запрос."
)
