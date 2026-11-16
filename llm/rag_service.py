from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CORE_DIR = HERE / "submission"
if CORE_DIR.is_dir() and str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import kb
from assistant import Assistant
from llm_client import log, make_client

KB_NAMES = ("knowledge-base.zip", "kb.zip", "knowledge_base.zip")
MAX_HISTORY = 10
QUOTE_CHARS = 400

NOTE_RE = re.compile(r"\s*\[Редакция:[^\]]*\]")


def find_knowledge_base() -> Path | None:
    explicit = os.getenv("KB_PATH", "").strip()
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    for root in (Path(os.getenv("DATA_DIR", "data")), HERE / "data", HERE.parent / "data", Path.cwd() / "data"):
        for name in KB_NAMES:
            path = root / name
            if path.is_file():
                return path
    return None


class RagService:
    def __init__(self) -> None:
        self.assistant: Assistant | None = None
        self.client = None
        self.kb_path: Path | None = None
        self.error = "Knowledge base is not loaded"

    @property
    def ready(self) -> bool:
        return self.assistant is not None

    def load(self) -> None:
        self.kb_path = find_knowledge_base()
        if self.kb_path is None:
            self.error = "Knowledge base archive not found in DATA_DIR"
            log(self.error)
            return
        try:
            assistant = Assistant.from_archive(self.kb_path)
        except Exception as exc:
            self.error = f"Knowledge base could not be loaded: {type(exc).__name__}"
            log(self.error)
            return
        self.client = make_client()
        assistant.prepare(self.client)
        self.assistant = assistant
        log(f"knowledge base loaded: {len(assistant.documents)} documents from {self.kb_path.name}")

    def close(self) -> None:
        if self.client is not None:
            self.client.close()

    def status(self) -> dict[str, Any]:
        if not self.ready:
            return {"loaded": False, "detail": self.error}
        documents = self.assistant.documents
        return {
            "loaded": True,
            "documents": len(documents),
            "laws": sum(1 for doc in documents if doc.kind == "law"),
            "embeddings": self.assistant.retriever.vectors is not None,
        }

    def _question(self, question: str, history: list[dict[str, str]]) -> str:
        turns = [
            (item.get("role"), (item.get("content") or "").strip())
            for item in history
            if item.get("role") in ("user", "assistant") and (item.get("content") or "").strip()
        ]
        if turns and turns[-1] == ("user", question.strip()):
            turns.pop()
        while turns and turns[0][0] == "assistant":
            turns.pop(0)
        turns = turns[-MAX_HISTORY:]
        if not turns:
            return question.strip()
        lines = [f"{'Пользователь' if role == 'user' else 'Ассистент'}: {text}" for role, text in turns]
        lines.append(f"Пользователь: {question.strip()}")
        return "\n".join(lines)

    def answer(self, question: str, history: list[dict[str, str]]) -> dict[str, Any]:
        if not self.ready:
            raise RuntimeError(self.error)
        full_question = self._question(question, history)
        result = self.assistant.answer(self.client, full_question)
        sources = [self._source(chunk) for chunk in result.evidence]
        return {"text": result.text, "sources": sources, "mode": "model"}

    def _source(self, chunk: kb.Chunk) -> dict[str, Any]:
        doc = self.assistant.docs_by_id[chunk.doc_id]
        index = doc.chunks.index(chunk)
        chunk_id = f"{doc.doc_id}#{index}"
        text = NOTE_RE.sub("", chunk.text).strip()
        if doc.kind == "law":
            location = chunk.label.split(", ", 1)[1] if ", " in chunk.label else chunk.label
            section = doc.source or doc.short_name
        else:
            location = chunk.label.rsplit(", ", 1)[1] if ", " in chunk.label else None
            section = doc.title
        return {
            "doc_id": doc.doc_id,
            "chunk_id": chunk_id,
            "location": location,
            "section": section,
            "page": None,
            "quote": text[:QUOTE_CHARS],
            "chunks": [{"id": chunk_id, "page": None, "text": text}],
        }
