from __future__ import annotations

import os
from pathlib import Path


def env(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    return default if not value or value == name else value


def env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(float(env(name)))))
    except ValueError:
        return default


def env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(env(name))))
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
RERANKER_MODEL = env("RERANKER_MODEL", "cohere/rerank-5-fast")
RERANK_CANDIDATES = 30
RERANK_DOC_CHARS = 1500

TEMPERATURE = env_float("TEMPERATURE", 0.0, 0.0, 2.0)
MAX_TOKENS = env_int("MAX_TOKENS", 1024, 256, 8192)
MAX_WORKERS = env_int("MAX_WORKERS", 4, 1, 8)
SELF_CHECK = env("SELF_CHECK", "0").lower() in ("1", "true", "yes")

TIME_BUDGET_SECONDS = 17 * 60
REQUEST_TIMEOUT_SECONDS = 90.0

COMPANY_FULLTEXT_LIMIT = 60_000
LAW_CONTEXT_CHARS = 12_000
LAW_TOP_CHUNKS = 10

MAX_ANSWER_CHARS = 9_500
FALLBACK_ANSWER = (
    "Не удалось сформировать ответ по базе знаний из-за технической ошибки. "
    "Повторите запрос."
)
