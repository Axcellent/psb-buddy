from __future__ import annotations

import re

from kb import Chunk

REFUSAL_RE = re.compile(
    r"в базе знаний (?:нет|отсутств|не (?:найден|содерж|указан|определен))"
    r"|нет (?:сведений|документ|информаци|данных|положени)"
    r"|не (?:содержит|содержится|найден|указан|определен)"
    r"|ответить (?:невозможно|нельзя)|не могу ответить",
    re.IGNORECASE,
)
CITATION_RE = re.compile(r"(?:\bп\.|пункт|\bст\.|стать|\bч\.|част[ьи]|§)\s*\d", re.IGNORECASE)
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
ARTICLE_RE = re.compile(r"ст\. (\d+(?:\.\d+)?)")
CLAUSE_RE = re.compile(r"п\. (\d+(?:\.\d+)+)")


def _normal(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[   ]", " ", text)
    return re.sub(r"(?<=\d) (?=\d{3}(?!\d))", "", text)


def _numbers(text: str) -> set[str]:
    return {number.rstrip(".,") for number in NUMBER_RE.findall(_normal(text)) if len(number.rstrip(".,")) >= 2}


def is_plain_refusal(text: str) -> bool:
    low = _normal(text)
    return bool(REFUSAL_RE.search(low)) and not CITATION_RE.search(low)


def is_grounded(answer: str, chunks: list[Chunk], question: str) -> bool:
    source = " ".join(f"{chunk.label} {chunk.render()}" for chunk in chunks)
    allowed = _numbers(source) | _numbers(question)
    if not _numbers(answer) <= allowed:
        return False
    low = _normal(answer)
    for chunk in chunks:
        article = ARTICLE_RE.search(chunk.label)
        if article and re.search(rf"(?:ст\.|стать[а-я]*|§)\s*{re.escape(article.group(1))}(?![\d.]\d)", low):
            return True
        clause = CLAUSE_RE.search(chunk.label)
        if clause and re.search(rf"(?<![\d.]){re.escape(clause.group(1))}(?!\d)", low):
            return True
    return False
