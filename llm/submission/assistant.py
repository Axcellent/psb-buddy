from __future__ import annotations

from dataclasses import dataclass

import httpx

import config
import kb
import prompts
from editions import edition_warnings
from llm_client import LLMError, chat, log
from retrieval import Retriever


@dataclass
class Answer:
    text: str
    company_docs: list[kb.Document]
    company_chunks: list[kb.Chunk]
    law_chunks: list[kb.Chunk]


class Assistant:
    def __init__(self, documents: list[kb.Document]) -> None:
        self.documents = documents
        self.docs_by_id = {doc.doc_id: doc for doc in documents}
        self.company = [doc for doc in documents if doc.kind == "company"]
        company_size = sum(len(doc.text) for doc in self.company)
        self.company_fulltext = company_size <= config.COMPANY_FULLTEXT_LIMIT
        self.retriever = Retriever(documents, use_company=not self.company_fulltext)
        self.clauses = Retriever(documents, use_company=True)
        self.catalog = kb.catalog(documents)

    @classmethod
    def from_archive(cls, path) -> "Assistant":
        return cls(kb.load_documents(path))

    def prepare(self, client: httpx.Client | None) -> None:
        if client is not None:
            self.retriever.build_embeddings(client)

    def context(self, client: httpx.Client | None, question: str):
        turns = prompts.parse_dialog(question)
        found = self.retriever.search(client, prompts.retrieval_query(turns))
        law_chunks = self._with_full_articles([c for c in found if self.docs_by_id[c.doc_id].kind == "law"])
        company_chunks = [c for c in found if self.docs_by_id[c.doc_id].kind == "company"]
        company_docs = self.company if self.company_fulltext else []
        query = prompts.retrieval_query(turns)
        scored = self.clauses.scored(query, config.HINT_CANDIDATES)
        closest = [chunk for chunk, _ in scored]
        specific = [(chunk, score) for chunk, score in scored if "вводная часть" not in chunk.label]
        threshold = specific[0][1] * config.HINT_MIN_RATIO if specific else 0.0
        hints: list[kb.Chunk] = []
        per_doc: dict[str, int] = {}
        for chunk, score in specific:
            if score < threshold or per_doc.get(chunk.doc_id, 0) >= config.HINT_PER_DOCUMENT:
                continue
            per_doc[chunk.doc_id] = per_doc.get(chunk.doc_id, 0) + 1
            hints.append(chunk)
            if len(hints) >= config.HINT_LIMIT:
                break
        weights: dict[str, float] = {}
        for chunk, score in scored:
            if self.docs_by_id[chunk.doc_id].kind == "law":
                weights[chunk.doc_id] = weights.get(chunk.doc_id, 0.0) + score
        warnings: list[str] = []
        if weights and closest and self.docs_by_id[closest[0].doc_id].kind == "law":
            best = max(weights.values())
            leading = sorted((d for d in weights if weights[d] >= 0.6 * best), key=lambda d: -weights[d])
            dialog = " ".join(text for _, text in turns)
            for doc_id in leading[: config.EDITION_DOCUMENTS]:
                warnings.extend(edition_warnings(dialog, self.docs_by_id[doc_id]))
        messages = prompts.build_messages(
            turns, company_docs, company_chunks, law_chunks, self.docs_by_id, self.catalog, hints, warnings
        )
        return messages, company_docs, company_chunks, law_chunks

    def _with_full_articles(self, chunks: list[kb.Chunk]) -> list[kb.Chunk]:
        by_doc: dict[str, list[kb.Chunk]] = {}
        for chunk in chunks:
            by_doc.setdefault(chunk.doc_id, []).append(chunk)
        ranked = sorted(by_doc, key=lambda doc_id: -len(by_doc[doc_id]))
        full = [
            doc_id for doc_id in ranked if len(self.docs_by_id[doc_id].text) <= config.SMALL_ARTICLE_CHARS
        ][: config.MAX_FULL_ARTICLES]
        result: list[kb.Chunk] = []
        for doc_id, selected in by_doc.items():
            result.extend(self.docs_by_id[doc_id].chunks if doc_id in full else selected)
        return result

    def extract(self, question: str) -> str:
        turns = prompts.parse_dialog(question)
        ranked = self.clauses.top(prompts.retrieval_query(turns), 6)
        specific = [chunk for chunk in ranked if "вводная часть" not in chunk.label]
        found = (specific or ranked)[:2]
        if not found:
            return (
                "В базе знаний не найдено положений, которые отвечают на этот вопрос. "
                "Уточните, о каком документе, контрагенте или норме идёт речь."
            )
        parts = [f"{chunk.text.strip()[:380]} ({chunk.label})" for chunk in found]
        return prompts.clean_answer("По базе знаний: " + " ".join(parts))

    def answer(self, client: httpx.Client, question: str) -> Answer:
        messages, company_docs, company_chunks, law_chunks = self.context(client, question)
        draft = chat(client, messages)
        if config.SELF_CHECK:
            review = [*messages, {"role": "assistant", "content": draft}, {"role": "user", "content": prompts.SELF_CHECK_PROMPT}]
            try:
                draft = chat(client, review)
            except LLMError as exc:
                log(f"self-check skipped: {exc}")
        text = prompts.clean_answer(draft)
        return Answer(text, company_docs, company_chunks, law_chunks)
