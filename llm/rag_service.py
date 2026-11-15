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
from grounding import is_plain_refusal
from llm_client import LLMError, log, make_client

KB_NAMES = ("knowledge-base.zip", "kb.zip", "knowledge_base.zip")
MAX_HISTORY = 10
MAX_SOURCES = 6
QUOTE_CHARS = 400

NOTE_RE = re.compile(r"\s*\[Редакция:[^\]]*\]")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z«(])")
CLAUSE_REF_RE = re.compile(r"(?:\bп\.|\bпп\.|пункт[а-яё]*)\s*((?:\d+\.\d+(?:\.\d+)*)(?:\s*(?:,|и)\s*\d+\.\d+(?:\.\d+)*)*)", re.IGNORECASE)
CLAUSE_NUMBER_RE = re.compile(r"\d+\.\d+(?:\.\d+)*")
ARTICLE_REF_RE = re.compile(r"(?:\bст\.|стать[а-яё]*|§)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
PART_REF_RE = re.compile(r"(?:\bп\.|пункт[а-яё]*|\bч\.|част[ьи][а-яё]*)\s*(\d+(?:\.\d+)*(?:-\d+)?)", re.IGNORECASE)
CODE_RE = re.compile(r"№\s*([А-ЯЁA-Z]{1,3}-\d+(?:/\d{4})?)")
YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _plain(text: str) -> str:
    text = text.lower().replace("ё", "е")
    return re.sub(r"[‐‑‒–—]", "-", text)


def find_knowledge_base() -> Path | None:
    explicit = os.getenv("KB_PATH", "").strip()
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    for root in (HERE / "data", HERE.parent / "data", Path.cwd() / "data"):
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
        self.keys: dict[str, list[str]] = {}

    @property
    def ready(self) -> bool:
        return self.assistant is not None

    def load(self) -> None:
        self.kb_path = find_knowledge_base()
        if self.kb_path is None:
            self.error = "Knowledge base archive not found: set KB_PATH or put knowledge-base.zip into ./data"
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
        self.keys = {doc.doc_id: self._document_keys(doc) for doc in assistant.documents if doc.kind == "company"}
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

    @staticmethod
    def _document_keys(doc: kb.Document) -> list[str]:
        head = "\n".join(doc.text.split("\n")[:4])
        title = _plain(doc.title)
        if title.startswith("доп"):
            return ["соглашени"]
        keys = [_plain(code) for code in CODE_RE.findall(head)]
        if "регламент" in title:
            keys.append("регламент")
        if "записк" in title:
            keys.append("записк")
        if "письм" in title:
            keys.append("письм")
        return keys

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
        try:
            result = self.assistant.answer(self.client, full_question)
            text, hints, mode = result.text, result.hints, "model"
        except LLMError as exc:
            log(f"model unavailable, answering from the knowledge base: {exc}")
            text, hints, mode = self.assistant.extract(full_question), [], "extract"
        sources = self._sources(text, hints)
        return {"text": text, "sources": sources, "mode": mode}

    def _company_documents(self, sentence: str, previous: list[kb.Document]) -> list[kb.Document]:
        low = _plain(sentence)
        found = []
        for doc in self.assistant.company:
            keys = self.keys.get(doc.doc_id, [])
            if any(key in low for key in keys):
                found.append(doc)
        regulations = [doc for doc in found if "регламент" in _plain(doc.title)]
        if len(regulations) > 1:
            years = set(YEAR_RE.findall(low))
            by_year = [doc for doc in regulations if years & set(YEAR_RE.findall(doc.title))]
            keep = by_year or [doc for doc in regulations if "утратил" not in _plain(doc.title)] or regulations[:1]
            found = [doc for doc in found if doc not in regulations or doc in keep]
        return found or previous

    def _sources(self, text: str, hints: list[kb.Chunk]) -> list[dict[str, Any]]:
        chunks: list[kb.Chunk] = []

        def add(chunk: kb.Chunk | None) -> None:
            if chunk is not None and chunk not in chunks:
                chunks.append(chunk)

        laws = {article: doc for doc in self.assistant.documents if doc.kind == "law" for article in doc.articles}
        mentioned: list[kb.Document] = []
        for sentence in SENTENCE_RE.split(text):
            for article in ARTICLE_REF_RE.findall(sentence):
                doc = laws.get(article)
                if doc is None:
                    continue
                parts = [p for p in PART_REF_RE.findall(sentence) if p != article]
                exact = [
                    chunk for chunk in doc.chunks
                    if any(re.search(rf"ст\. {re.escape(article)}, (?:п|ч)\. {re.escape(part)}(?![\d.-])", chunk.label) for part in parts)
                ]
                add(exact[0] if exact else next((c for c in doc.chunks if f"ст. {article}" in c.label), None))
            mentioned = self._company_documents(sentence, mentioned)
            numbers = [n for group in CLAUSE_REF_RE.findall(sentence) for n in CLAUSE_NUMBER_RE.findall(group)]
            candidates = mentioned or self.assistant.company
            for number in numbers:
                for doc in candidates:
                    match = next((c for c in doc.chunks if c.label.endswith(f"п. {number}")), None)
                    if match is not None:
                        add(match)
                        break
            if not numbers:
                for doc in mentioned:
                    if not any(", п. " in c.label for c in doc.chunks):
                        add(doc.chunks[0] if doc.chunks else None)
        if not chunks and not is_plain_refusal(text):
            for chunk in hints[:2]:
                add(chunk)
        return [self._source(chunk) for chunk in chunks[:MAX_SOURCES]]

    def _source(self, chunk: kb.Chunk) -> dict[str, Any]:
        doc = self.assistant.docs_by_id[chunk.doc_id]
        index = doc.chunks.index(chunk) if chunk in doc.chunks else 0
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
