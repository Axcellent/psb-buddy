from __future__ import annotations

import re
from datetime import date

from kb import Document

MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
MONTH_RE = r"(январ[яе]|феврал[яе]|марта|марте|апрел[яе]|ма[яе]|июн[яе]|июл[яе]|августа|августе|сентябр[яе]|октябр[яе]|ноябр[яе]|декабр[яе])"
FULL_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
DAY_MONTH_RE = re.compile(rf"\b(\d{{1,2}})\s+{MONTH_RE}\s+(\d{{4}})", re.IGNORECASE)
MONTH_YEAR_RE = re.compile(rf"\b{MONTH_RE}\s+(\d{{4}})", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(20\d{2})\s*(?:году|года|год|г\.|г\b)", re.IGNORECASE)
CHANGE_DATE_RE = re.compile(rf"с\s+(\d{{1,2}})\s+{MONTH_RE}\s+(\d{{4}})", re.IGNORECASE)
NOTE_RE = re.compile(r"\[Редакция:([^\]]*)\]")


def _month(word: str) -> int:
    word = word.lower()
    for stem, number in sorted(MONTHS.items(), key=lambda item: -len(item[0])):
        if word.startswith(stem):
            return number
    return 1


def _safe(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def question_dates(text: str) -> list[date]:
    found: list[date | None] = []
    for day, month, year in FULL_DATE_RE.findall(text):
        found.append(_safe(int(year), int(month), int(day)))
    rest = FULL_DATE_RE.sub(" ", text)
    for day, month, year in DAY_MONTH_RE.findall(rest):
        found.append(_safe(int(year), _month(month), int(day)))
    rest = DAY_MONTH_RE.sub(" ", rest)
    for month, year in MONTH_YEAR_RE.findall(rest):
        found.append(_safe(int(year), _month(month), 1))
    rest = MONTH_YEAR_RE.sub(" ", rest)
    for year in YEAR_RE.findall(rest):
        found.append(_safe(int(year), 1, 1))
    return sorted(d for d in found if d is not None)


def _changes(text: str) -> list[tuple[date, str]]:
    result = []
    for note in text.split(";"):
        match = CHANGE_DATE_RE.search(note)
        if not match:
            continue
        changed = _safe(int(match.group(3)), _month(match.group(2)), int(match.group(1)))
        if changed:
            result.append((changed, note.strip()))
    return result


SUBJECT_RE = re.compile(r"^(Пункт|Подпункт|Часть)\s+([\d.\-]+)", re.IGNORECASE)
ADDED_RE = re.compile(r"дополнен\w*\s+(пунктом|подпунктом|частью)\s+([\d.\-]+)", re.IGNORECASE)
KINDS = {"пункт": "п.", "пунктом": "п.", "подпункт": "подп.", "подпунктом": "подп.", "часть": "ч.", "частью": "ч."}


def _subject(text: str) -> str:
    added = ADDED_RE.search(text)
    if added:
        return f"{KINDS[added.group(1).lower()]} {added.group(2).rstrip('.')} (добавлен)"
    subject = SUBJECT_RE.match(text)
    if subject:
        return f"{KINDS[subject.group(1).lower()]} {subject.group(2).rstrip('.')}"
    if text.lower().startswith("статья"):
        return "статья в целом"
    if text.lower().startswith("абзац"):
        return "отдельные абзацы"
    return text


def _exported(doc: Document) -> date | None:
    match = FULL_DATE_RE.search(doc.exported or "")
    if not match:
        return None
    return _safe(int(match.group(3)), int(match.group(2)), int(match.group(1)))


def edition_warnings(question: str, doc: Document | None, limit: int = 6) -> list[str]:
    dates = question_dates(question)
    if not dates or doc is None or doc.kind != "law":
        return []
    event = dates[0]
    exported = _exported(doc)
    notes = [note for found in NOTE_RE.findall(doc.text) for note in _changes(found)]
    notes += [note for change in doc.changes for note in _changes(change)]
    relevant = sorted(
        {(changed, text) for changed, text in notes if changed > event and (exported is None or changed <= exported)},
        reverse=True,
    )
    if not relevant:
        return []
    by_date: dict[date, list[str]] = {}
    for changed, text in relevant:
        subject = _subject(text)
        if subject not in by_date.setdefault(changed, []):
            by_date[changed].append(subject)
    articles = ", ".join(doc.articles) or "текст"
    warnings = [
        f"{doc.short_name}, ст. {articles}: вопрос относится к периоду с {event:%d.%m.%Y}. "
        "Перечисленные ниже положения действуют в нынешней редакции только с указанных дат; "
        "прежних редакций в базе знаний нет, поэтому на более ранний период их применять нельзя."
    ]
    for changed in sorted(by_date, reverse=True)[:limit]:
        warnings.append(f"с {changed:%d.%m.%Y}: {', '.join(sorted(by_date[changed]))}")
    return warnings
