"""Общие настройки API; переменные процесса имеют приоритет над .env."""

import math
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

LLM_SERVICE_URL = (
    os.getenv("LLM_SERVICE_URL", "").strip()
    or os.getenv("AI_SERVICE_URL", "").strip()
    or "http://localhost:8001"
).rstrip("/")

AI_TIMEOUT = float(
    os.getenv("AI_TIMEOUT_SECONDS", "").strip()
    or os.getenv("LLM_SERVICE_TIMEOUT", "").strip()
    or "300"
)
if not math.isfinite(AI_TIMEOUT) or AI_TIMEOUT <= 0:
    raise ValueError("AI_TIMEOUT_SECONDS must be a positive finite number")

def directory(name: str, default: str) -> Path:
    path = Path(os.getenv(name, "").strip() or default)
    return path if path.is_absolute() else ROOT / path


DOCUMENTS_DIR = directory("DOCUMENTS_DIR", "backend/documents")
DATA_DIR = directory("DATA_DIR", "data")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{ROOT / 'backend' / 'app.db'}")
