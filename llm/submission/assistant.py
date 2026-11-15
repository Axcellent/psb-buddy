from __future__ import annotations

from dataclasses import dataclass, field

import httpx

import config
import kb
import prompts
from editions import (
    VAT_QUESTION_RE,
    correction_prompt,
    edition_finding,
    template_answer,
    vat_conflicts,
    violation,
)
from grounding import is_grounded, is_plain_refusal
from llm_client import LLMError, chat, is_too_long, log
from retrieval import Retriever


@dataclass
class Answer:
    text: str
    company_docs: list[kb.Document]
    company_chunks: list[kb.Chunk]
    law_chunks: list[kb.Chunk]
    hints: list[kb.Chunk] = field(default_factory=list)


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
        self.vat_notes = vat_conflicts(documents)
        self.compact = False
        self.overflows = 0

    @classmethod
    def from_archive(cls, path) -> "Assistant":
        return cls(kb.load_documents(path))

    def prepare(self, client: httpx.Client | None) -> None:
        if client is not None:
            self.retriever.build_embeddings(client)

    def context(self, client: httpx.Client | None, question: str):
        return self._prepare(client, question)[:4]

    def _prepare(self, client: httpx.Client | None, question: str, compact: bool = False):
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
        dialog = " ".join(text for _, text in turns)
        findings = [
            finding
            for doc in self.documents
            if doc.kind == "law" and (finding := edition_finding(dialog, doc)) is not None
        ]
        warnings: list[str] = []
        if weights and closest and self.docs_by_id[closest[0].doc_id].kind == "law":
            best = max(weights.values())
            leading = sorted((d for d in weights if weights[d] >= 0.6 * best), key=lambda d: -weights[d])
            for doc_id in leading[: config.EDITION_DOCUMENTS]:
                for finding in findings:
                    if finding.doc.doc_id == doc_id:
                        warnings.extend(finding.lines())
        if self.vat_notes and VAT_QUESTION_RE.search(dialog):
            warnings.extend(self.vat_notes)
        if compact:
            totals: dict[str, float] = {}
            for chunk, score in scored:
                if self.docs_by_id[chunk.doc_id].kind == "company":
                    totals[chunk.doc_id] = totals.get(chunk.doc_id, 0.0) + score
            keep = sorted(totals, key=lambda doc_id: -totals[doc_id])[: config.COMPACT_COMPANY_DOCUMENTS]
            company_docs = [doc for doc in company_docs if doc.doc_id in keep]
            law_chunks = [c for c in found if self.docs_by_id[c.doc_id].kind == "law"][: config.COMPACT_LAW_CHUNKS]
            hints = hints[: config.COMPACT_HINTS]
        messages = prompts.build_messages(
            turns, company_docs, company_chunks, law_chunks, self.docs_by_id, self.catalog, hints, warnings, compact
        )
        support: list[kb.Chunk] = []
        for chunk in [*hints, *found, *closest[: config.RECHECK_CLOSEST]]:
            if chunk not in support and "вводная часть" not in chunk.label:
                support.append(chunk)
        support = support[: config.RECHECK_LIMIT]
        return messages, company_docs, company_chunks, law_chunks, findings, hints, turns, support

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
        prepared = self._prepare(client, question, self.compact)
        try:
            draft = chat(client, prepared[0])
        except LLMError as exc:
            if self.compact or not is_too_long(exc):
                raise
            self.overflows += 1
            if self.overflows >= 2:
                self.compact = True
            log(f"request too long for the model, retrying with a compact context: {exc}")
            prepared = self._prepare(client, question, True)
            draft = chat(client, prepared[0])
        messages, company_docs, company_chunks, law_chunks, findings, hints, turns, support = prepared
        if config.SELF_CHECK:
            review = [*messages, {"role": "assistant", "content": draft}, {"role": "user", "content": prompts.SELF_CHECK_PROMPT}]
            try:
                draft = chat(client, review)
            except LLMError as exc:
                log(f"self-check skipped: {exc}")
        draft = self._check_editions(client, messages, draft, findings)
        draft = self._recheck_refusal(client, turns, draft, support)
        text = prompts.clean_answer(draft)
        return Answer(text, company_docs, company_chunks, law_chunks, hints)

    def _recheck_refusal(self, client: httpx.Client, turns, draft: str, hints: list[kb.Chunk]) -> str:
        if not hints or not is_plain_refusal(draft):
            return draft
        try:
            second = chat(client, prompts.build_recheck(turns, hints, self.docs_by_id))
        except LLMError as exc:
            log(f"refusal recheck skipped: {exc}")
            return draft
        if second.strip(" .!»«\"").upper() == "НЕТ" or is_plain_refusal(second):
            return draft
        if not is_grounded(second, hints, " ".join(text for _, text in turns)):
            log("refusal recheck: new answer is not grounded in the fragments, keeping the refusal")
            return draft
        log("refusal recheck: answer found in the closest fragments")
        return second

    def _check_editions(self, client: httpx.Client, messages: list[dict[str, str]], draft: str, findings) -> str:
        for finding in findings:
            hits = violation(draft, finding)
            if not hits:
                continue
            log(f"edition check: answer applies {finding.name} to an earlier period, correcting")
            review = [
                *messages,
                {"role": "assistant", "content": draft},
                {"role": "user", "content": correction_prompt(finding, hits)},
            ]
            try:
                fixed = chat(client, review)
            except LLMError as exc:
                log(f"edition correction failed: {exc}")
                fixed = ""
            if fixed and not violation(fixed, finding):
                return fixed
            return template_answer(finding, hits)
        return draft
