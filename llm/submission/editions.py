from __future__ import annotations

import re
from dataclasses import dataclass
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
        found.append(_safe(int(year), _month(month), 28))
    rest = MONTH_YEAR_RE.sub(" ", rest)
    for year in YEAR_RE.findall(rest):
        found.append(_safe(int(year), 12, 31))
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


@dataclass
class Finding:
    doc: Document
    event: date
    changes: list[tuple[date, str]]

    @property
    def name(self) -> str:
        return f"{self.doc.short_name}, ст. {', '.join(self.doc.articles) or 'текст'}"

    def lines(self, limit: int = 6) -> list[str]:
        by_date: dict[date, list[str]] = {}
        for changed, subject in self.changes:
            if subject not in by_date.setdefault(changed, []):
                by_date[changed].append(subject)
        result = [
            f"{self.name}: вопрос относится к периоду до {self.event:%d.%m.%Y} включительно. "
            "Перечисленные ниже положения действуют в нынешней редакции только с указанных дат; "
            "прежних редакций в базе знаний нет, поэтому на более ранний период их применять нельзя."
        ]
        for changed in sorted(by_date, reverse=True)[:limit]:
            result.append(f"с {changed:%d.%m.%Y}: {', '.join(sorted(by_date[changed]))}")
        return result


def edition_finding(question: str, doc: Document | None) -> Finding | None:
    dates = question_dates(question)
    if not dates or doc is None or doc.kind != "law":
        return None
    event = dates[0]
    exported = _exported(doc)
    notes = [note for found in NOTE_RE.findall(doc.text) for note in _changes(found)]
    notes += [note for change in doc.changes for note in _changes(change)]
    changes = sorted(
        {(changed, _subject(text)) for changed, text in notes
         if changed > event and (exported is None or changed <= exported)},
        reverse=True,
    )
    return Finding(doc, event, changes) if changes else None


ARTICLE_REF_RE = re.compile(r"(?:ст\.|стать[а-я]*|§)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
POINT_REF_RE = re.compile(r"(?:п\.|пункт[а-я]*|ч\.|част[ьи][а-я]*)\s*(\d+(?:\.\d+)*(?:-\d+)?)", re.IGNORECASE)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)*(?:-\d+)?")
ACK_RE = re.compile(
    r"прежн|предыдущ|только (?:в )?действующ|редакци[а-я]*[^.]{0,60}(?:\bнет\b|отсутств)"
    r"|нельзя (?:назвать|подтвердить|установить|определить)|не (?:могу|можем|удастся) подтвердить",
    re.IGNORECASE,
)
MONTH_NAMES = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _spoken(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month]} {value.year}"


def violation(answer: str, finding: Finding) -> list[tuple[date, str]]:
    low = answer.lower().replace("ё", "е")
    if not set(ARTICLE_REF_RE.findall(low)) & set(finding.doc.articles):
        return []
    if ACK_RE.search(low):
        return []
    for changed, _ in finding.changes:
        if f"{changed:%d.%m.%Y}" in low or _spoken(changed) in low:
            return []
    points = set(POINT_REF_RE.findall(low))
    if not points:
        return finding.changes
    hits = []
    for changed, subject in finding.changes:
        number = NUMBER_RE.search(subject)
        if subject == "статья в целом" or (number and number.group(0) in points):
            hits.append((changed, subject))
    return hits


def _described(hits: list[tuple[date, str]]) -> str:
    return "; ".join(f"{subject} — с {_spoken(changed)} г" for changed, subject in hits[:3])


def correction_prompt(finding: Finding, hits: list[tuple[date, str]]) -> str:
    return (
        f"В ответе ошибка с редакцией закона. Вопрос относится к периоду до {finding.event:%d.%m.%Y}, "
        f"а {finding.name} в базе знаний есть только в действующей редакции: {_described(hits)}. "
        "Прежней редакции в базе знаний нет, поэтому применять нынешнюю норму к тому периоду нельзя. "
        "Перепиши ответ: прямо скажи, что по базе знаний нельзя подтвердить, что действовало в тот период, "
        "назови дату изменения нормы и не называй нынешнее значение как действовавшее тогда. "
        "Выведи только исправленный ответ."
    )


def template_answer(finding: Finding, hits: list[tuple[date, str]]) -> str:
    return (
        f"По базе знаний ответить на этот вопрос нельзя. {finding.name} приведена только в действующей редакции: "
        f"{_described(hits)}. Вопрос относится к более раннему периоду, а прежней редакции этой нормы в базе знаний нет, "
        "поэтому подтвердить, что действовало тогда, по документам невозможно. "
        "Для ответа нужна редакция, действовавшая на дату события."
    )


VAT_CONTRACT_RE = re.compile(r"НДС по ставке (\d{1,2}) ?%")
VAT_LAW_RE = re.compile(r"налоговой ставке (\d{1,2}) процент\w* в случаях, не указанных")
VAT_QUESTION_RE = re.compile(r"\bндс\b|добавленн\w+ стоимост", re.IGNORECASE)


def vat_conflicts(documents: list[Document]) -> list[str]:
    general = None
    for doc in documents:
        if doc.kind != "law":
            continue
        for chunk in doc.chunks:
            match = VAT_LAW_RE.search(chunk.text)
            if match:
                general = (match.group(1), chunk.label)
                break
        if general:
            break
    if not general:
        return []
    notes = []
    for doc in documents:
        if doc.kind != "company":
            continue
        for chunk in doc.chunks:
            match = VAT_CONTRACT_RE.search(chunk.text)
            if match and match.group(1) != general[0]:
                notes.append(
                    f"Расхождение договора и закона: в документе «{chunk.label}» указан НДС по ставке {match.group(1)}%, "
                    f"а действующая общая ставка по закону — {general[0]}% ({general[1]}). "
                    "Если вопрос о ставке НДС по этому договору, назови оба значения со ссылками и укажи на расхождение."
                )
    return notes
