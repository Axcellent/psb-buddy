from __future__ import annotations

import math
import re
from collections import Counter

import httpx
import numpy as np

import config
from kb import Chunk, Document
from llm_client import LLMError, embed, log, rerank

WORD_RE = re.compile(r"[0-9a-zа-я]+(?:[.-][0-9]+)*")
STEM_LEN = 5
STOPWORDS = {
    "и", "в", "во", "на", "по", "с", "со", "к", "ко", "о", "об", "от", "до", "за", "из",
    "у", "не", "ли", "а", "но", "или", "что", "как", "это", "то", "же", "для", "при",
    "мы", "нас", "наш", "наши", "нам", "вы", "он", "она", "они", "их", "его", "ее",
    "ли", "бы", "да", "нет", "есть", "быть", "был", "была", "если", "можно", "нужно",
    "какой", "какая", "какие", "каков", "сколько", "ли", "ст", "п", "ч", "рф",
}
ALIASES = {
    "мрот": "минимальный размер оплаты труда",
    "пдн": "персональные данные",
    "сверхурочк": "сверхурочная работа",
    "испытательн": "испытание при приеме на работу",
    "штраф": "административная ответственность налоговые санкции",
}


def tokens(text: str) -> list[str]:
    text = text.lower().replace("ё", "е")
    result = []
    for word in WORD_RE.findall(text):
        if word in STOPWORDS:
            continue
        if word.isalpha():
            if len(word) < 2:
                continue
            word = word[:STEM_LEN]
        result.append(word)
    return result


def expand_query(text: str) -> str:
    lower = text.lower()
    extra = [expansion for key, expansion in ALIASES.items() if key in lower]
    return " ".join([text, *extra])


class BM25:
    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.5) -> None:
        self.k1, self.b = k1, b
        self.freqs = [Counter(doc) for doc in documents]
        self.lengths = [len(doc) for doc in documents]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df: Counter[str] = Counter()
        for doc in documents:
            df.update(set(doc))
        n = len(documents)
        self.idf = {term: math.log(1 + (n - f + 0.5) / (f + 0.5)) for term, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        result = []
        for freq, length in zip(self.freqs, self.lengths):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * length / (self.avg or 1.0))
            for term in set(query):
                tf = freq.get(term)
                if tf:
                    score += self.idf.get(term, 0.0) * tf * (self.k1 + 1) / (tf + norm)
            result.append(score)
        return result


MAX_ATTACHED_OUTLINES = 2


def _article_of(chunk: Chunk) -> str | None:
    match = re.search(r", ст\. (\d+(?:\.\d+)*)", chunk.label)
    return match.group(1) if match else None


def _index_text(chunk: Chunk, doc: Document) -> str:
    return f"{doc.short_name or doc.title} {doc.topic} {chunk.label} {chunk.context} {chunk.text}"


class Retriever:
    def __init__(self, documents: list[Document], use_company: bool) -> None:
        self.docs = {doc.doc_id: doc for doc in documents}
        kinds = {"law", "company"} if use_company else {"law"}
        self.chunks = [
            c
            for doc in documents
            if doc.kind in kinds
            for c in (*doc.chunks, *doc.outlines.values())
        ]
        texts = [_index_text(c, self.docs[c.doc_id]) for c in self.chunks]
        self.bm25 = BM25([tokens(t) for t in texts])
        self._texts = texts
        self.vectors: np.ndarray | None = None
        self.rerank_enabled = True

    def build_embeddings(self, client: httpx.Client) -> None:
        if not self.chunks:
            return
        try:
            vectors = embed(client, [t[:2000] for t in self._texts])
        except (LLMError, httpx.HTTPError) as exc:
            log(f"embeddings unavailable, using BM25 only: {exc}")
            return
        matrix = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        self.vectors = matrix / np.where(norms == 0, 1, norms)
        log(f"embeddings ready: {matrix.shape[0]} fragments")

    def _rerank(self, client: httpx.Client | None, query: str, ordered: list[int]) -> list[int]:
        if client is None or not self.rerank_enabled or len(ordered) < 2:
            return ordered
        head, tail = ordered[: config.RERANK_CANDIDATES], ordered[config.RERANK_CANDIDATES:]
        documents = [
            f"{self.chunks[i].label}\n{self.chunks[i].render()}"[: config.RERANK_DOC_CHARS] for i in head
        ]
        question = "\n".join(dict.fromkeys(query.split("\n")))[:2000]
        try:
            order = rerank(client, question, documents)
        except (LLMError, httpx.HTTPError) as exc:
            self.rerank_enabled = False
            log(f"reranker unavailable, keeping fused order: {exc}")
            return ordered
        ranked = [head[i] for i in order]
        ranked.extend(i for i in head if i not in ranked)
        return ranked + tail

    def search(self, client: httpx.Client | None, query: str) -> list[Chunk]:
        if not self.chunks:
            return []
        expanded = expand_query(query)
        bm25 = self.bm25.scores(tokens(expanded))
        rankings = [sorted(range(len(bm25)), key=lambda i: bm25[i], reverse=True)]
        if self.vectors is not None and client is not None:
            try:
                q = np.asarray(embed(client, [expanded[:2000]])[0], dtype=np.float32)
                q /= np.linalg.norm(q) or 1.0
                dense = self.vectors @ q
                rankings.append(list(np.argsort(-dense)))
            except (LLMError, httpx.HTTPError) as exc:
                log(f"query embedding failed, BM25 only: {exc}")
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, index in enumerate(ranking[:60]):
                fused[int(index)] = fused.get(int(index), 0.0) + 1.0 / (60 + rank)
        ordered = sorted(fused, key=fused.get, reverse=True)
        if len(rankings) == 1:
            ordered = [i for i in ordered if bm25[i] > 0]
        ordered = self._rerank(client, query, ordered)

        selected: list[Chunk] = []
        used = 0
        for index in ordered:
            chunk = self.chunks[index]
            size = len(chunk.render())
            if used + size > config.LAW_CONTEXT_CHARS and selected:
                continue
            selected.append(chunk)
            used += size
            if len(selected) >= config.LAW_TOP_CHUNKS:
                break

        attached = 0
        for chunk in list(selected):
            if attached >= MAX_ATTACHED_OUTLINES:
                break
            article = _article_of(chunk)
            outline = self.docs[chunk.doc_id].outlines.get(article or "")
            if outline is not None and outline not in selected:
                selected.append(outline)
                attached += 1

        order = {id(c): n for n, c in enumerate(self.chunks)}
        return sorted(selected, key=lambda c: order[id(c)])
