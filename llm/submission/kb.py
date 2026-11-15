from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from llm_client import log

TEXT_SUFFIXES = {".txt", ".md"}
DOCX_SUFFIX = ".docx"

LAW_PREFIXES = ("законы",)
HEADER_PREFIXES = ("Источник:", "URL:", "Дата выгрузки:")

ARTICLE_RE = re.compile(r"^Статья\s+(\d+(?:\.\d+)*)\.\s+\S")
POINT_RE = re.compile(r"^(\d+(?:\.\d+)*(?:-\d+)?)\.\s+\S")
SUBPOINT_RE = re.compile(r"^(\d+(?:\.\d+)*(?:-\d+)?)\)\s+\S")
NOTES_RE = re.compile(r"^Примечани[ея]\s*[.:]?\s*$")
CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)+)\.\s+\S")

EDITORIAL_RE = re.compile(
    r"\s[-–—]\s*Федеральн\w*\s+закон\w*\s+от"
    r"|^(Федеральн\w*\s+закон\w*\s+от|См\.\s|Обратите внимание|О проверке конституционности"
    r"|Информация об изменениях|ГАРАНТ)"
)

CHANGE_RE = re.compile(
    r"^((Статья|Пункт|Подпункт|Часть|Абзац|Примечани\w*|Наименование)\b.*?"
    r"(изменен\w*|дополнен\w*|утратил\w*|введен\w*).*?\sс\s+\d{1,2}\s+\S+\s+\d{4}\s*г\.?)",
    re.IGNORECASE,
)
WHOLE_ARTICLE_CHANGE_RE = re.compile(r"^Статья\s+[\d.]+\s+изменен", re.IGNORECASE)
NOTE_SUFFIX_RE = re.compile(r"\s\[Редакция:[^\]]*\]$")

AI_ADDRESS_RE = re.compile(
    r"(\bИИ\b|\bAI\b|\bLLM\b|нейросет|языков\w*\s+модел|чат-?бот|system prompt|системн\w*\s+промпт)",
    re.IGNORECASE,
)
COMMAND_RE = re.compile(
    r"(игнорируй|не упоминай|отвечай|забудь|выполняй|не сообщай|ignore|disregard)", re.IGNORECASE
)

LAW_CODES = (
    ("НК РФ", "НК РФ"), ("Налоговый кодекс", "НК РФ"),
    ("ТК РФ", "ТК РФ"), ("Трудовой кодекс", "ТК РФ"),
    ("КоАП РФ", "КоАП РФ"), ("административных правонарушениях", "КоАП РФ"),
    ("ГК РФ", "ГК РФ"), ("Гражданский кодекс", "ГК РФ"),
)

MAX_CHUNK_CHARS = 1600
OUTLINE_SENTENCE_CHARS = 220

NK_CHAPTERS = (
    (106, 142, "налоговые правонарушения и ответственность"),
    (143, 178, "налог на добавленную стоимость (НДС)"),
    (207, 233, "налог на доходы физических лиц (НДФЛ)"),
    (246, 333, "налог на прибыль организаций"),
)


def nk_topic(article: str) -> str:
    try:
        number = int(article.split(".")[0])
    except ValueError:
        return ""
    for low, high, topic in NK_CHAPTERS:
        if low <= number <= high:
            return topic
    return ""


@dataclass
class Chunk:
    doc_id: str
    label: str
    text: str
    context: str = ""

    def render(self) -> str:
        if self.context:
            return f"[{self.context}]\n{self.text}"
        return self.text


@dataclass
class Document:
    doc_id: str
    kind: str
    title: str
    text: str
    short_name: str = ""
    source: str = ""
    topic: str = ""
    exported: str = ""
    changes: list[str] = field(default_factory=list)
    articles: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    outlines: dict[str, Chunk] = field(default_factory=dict)


def _fix_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    raw = name.encode("cp437", errors="replace")
    for encoding in ("utf-8", "cp866", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return name


def _read_docx(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as doc:
        root = ET.fromstring(doc.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return "\n".join(
        "".join(node.text or "" for node in paragraph.iter(ns + "t"))
        for paragraph in root.iter(ns + "p")
    )


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_archive(path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = _fix_name(info)
            if info.is_dir() or name.startswith("__MACOSX/"):
                continue
            suffix = PurePosixPath(name).suffix.lower()
            if suffix not in TEXT_SUFFIXES and suffix != DOCX_SUFFIX:
                continue
            try:
                raw = archive.read(info)
                text = _read_docx(raw) if suffix == DOCX_SUFFIX else _decode(raw)
            except (KeyError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
                log(f"skipped unreadable document: {type(exc).__name__}")
                continue
            if text.strip():
                files.append((name, text.replace("\r\n", "\n").replace("\r", "\n")))
    files.sort()
    return files


def sanitize(text: str) -> tuple[str, int]:
    kept, dropped = [], 0
    for line in text.split("\n"):
        if AI_ADDRESS_RE.search(line) and COMMAND_RE.search(line):
            dropped += 1
            continue
        kept.append(line)
    return "\n".join(kept), dropped


def _doc_id(name: str) -> str:
    return PurePosixPath(name).stem


def _is_law(name: str, text: str) -> bool:
    base = PurePosixPath(name).name.lower()
    parts = [p.lower() for p in PurePosixPath(name).parts]
    if any(base.startswith(prefix) for prefix in LAW_PREFIXES) or any(p in LAW_PREFIXES for p in parts[:-1]):
        return True
    head = text.lstrip()[:400]
    return head.startswith("Источник:") and "Статья" in head


def _law_short_name(source: str, fallback: str) -> str:
    for needle, short in LAW_CODES:
        if needle in source:
            return short
    match = re.search(r"N\s*(\d+-ФЗ)", source)
    if match:
        return f"Федеральный закон № {match.group(1)}"
    return fallback


def _law_paragraphs(text: str) -> tuple[dict[str, str], list[str], list[str]]:
    header: dict[str, str] = {}
    paragraphs: list[str] = []
    changes: list[str] = []
    pending: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.replace("\xa0", " ").strip()
        if not line:
            continue
        if line.startswith(HEADER_PREFIXES):
            key, _, value = line.partition(":")
            header[key] = value.strip()
            continue
        if EDITORIAL_RE.search(line):
            change = CHANGE_RE.match(line)
            if change:
                note = change.group(1)
                pending.append(note)
                if WHOLE_ARTICLE_CHANGE_RE.match(note):
                    changes.append(note)
            continue
        if pending:
            line = f"{line} [Редакция: {'; '.join(pending)}]"
            pending = []
        paragraphs.append(line)
    return header, paragraphs, changes


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    pieces, current = [], ""
    for paragraph in text.split("\n"):
        while len(paragraph) > MAX_CHUNK_CHARS:
            cut = paragraph.rfind(". ", 0, MAX_CHUNK_CHARS)
            cut = cut + 1 if cut > MAX_CHUNK_CHARS // 2 else MAX_CHUNK_CHARS
            if current:
                pieces.append(current)
                current = ""
            pieces.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if current and len(current) + len(paragraph) + 1 > MAX_CHUNK_CHARS:
            pieces.append(current)
            current = ""
        current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        pieces.append(current)
    return pieces


def _chunk_law(doc: Document, paragraphs: list[str]) -> None:
    term = "п." if doc.short_name == "НК РФ" else "ч."
    groups: list[tuple[str, str, list[str]]] = []

    article = None
    numbered = False
    point = sub = None
    point_intro = ""
    in_notes = False
    part = 0
    prev_end = "."

    def numbered_article(start: int) -> bool:
        for paragraph in paragraphs[start + 1:]:
            if ARTICLE_RE.match(paragraph):
                return False
            if POINT_RE.match(paragraph):
                return True
        return False

    for index, paragraph in enumerate(paragraphs):
        heading = ARTICLE_RE.match(paragraph)
        if heading:
            article = heading.group(1)
            doc.articles.append(article)
            numbered = numbered_article(index)
            point = sub = None
            point_intro = ""
            in_notes = False
            part = 0
            prev_end = "."
            groups.append((f"{doc.short_name}, ст. {article}", "", [paragraph]))
            continue
        if article is None:
            continue
        base = f"{doc.short_name}, ст. {article}"
        context = ""
        if NOTES_RE.match(NOTE_SUFFIX_RE.sub("", paragraph)):
            in_notes = True
            point = sub = None
            label = f"{base}, примечания"
        elif numbered and (m := POINT_RE.match(paragraph)):
            point, sub = m.group(1), None
            point_intro = paragraph[:300]
            label = f"{base}, примечание {point}" if in_notes else f"{base}, {term} {point}"
        elif numbered and (m := SUBPOINT_RE.match(paragraph)):
            sub = m.group(1)
            if term == "п.":
                label = f"{base}, подп. {sub} п. {point}" if point else f"{base}, подп. {sub}"
            else:
                label = f"{base}, п. {sub} ч. {point}" if point else f"{base}, п. {sub}"
            context = point_intro
        elif numbered:
            label = groups[-1][0] if groups else base
            context = groups[-1][1] if groups else ""
        else:
            if prev_end == "." or part == 0:
                part += 1
            label = f"{base}, ч. {part}"
        bare = NOTE_SUFFIX_RE.sub("", paragraph).rstrip()
        prev_end = bare[-1:] if bare else "."
        if groups and groups[-1][0] == label and groups[-1][1] == context:
            groups[-1][2].append(paragraph)
        else:
            groups.append((label, context, [paragraph]))

    merged: list[tuple[str, str, list[str]]] = []
    pending_heading = ""
    for label, context, paras in groups:
        if len(paras) == 1 and ARTICLE_RE.match(paras[0]):
            pending_heading = paras[0]
            continue
        if pending_heading:
            paras = [pending_heading, *paras]
            pending_heading = ""
        merged.append((label, context, paras))
    if pending_heading:
        merged.append((f"{doc.short_name}", "", [pending_heading]))

    for label, context, paras in merged:
        for piece in _split_long("\n".join(paras)):
            doc.chunks.append(Chunk(doc.doc_id, label, piece, context))
    _build_outlines(doc, paragraphs)


def _first_sentence(paragraph: str) -> str:
    number = re.match(r"^\S+\s+", paragraph)
    start = number.end() if number else 0
    end = paragraph.find(". ", start, OUTLINE_SENTENCE_CHARS)
    if end > 0:
        return paragraph[: end + 1]
    return paragraph if len(paragraph) <= OUTLINE_SENTENCE_CHARS else paragraph[:OUTLINE_SENTENCE_CHARS] + "…"


def _build_outlines(doc: Document, paragraphs: list[str]) -> None:
    article, heading, points = None, "", []

    def flush() -> None:
        if article and len(points) >= 3:
            text = "\n".join([heading, *points])
            label = f"{doc.short_name}, ст. {article}, основные пункты"
            doc.outlines[article] = Chunk(doc.doc_id, label, text)

    for paragraph in paragraphs:
        heading_match = ARTICLE_RE.match(paragraph)
        if heading_match:
            flush()
            article, heading, points = heading_match.group(1), paragraph, []
            continue
        point = POINT_RE.match(paragraph)
        if article and point and point.group(1).isdigit():
            note = NOTE_SUFFIX_RE.search(paragraph)
            sentence = _first_sentence(NOTE_SUFFIX_RE.sub("", paragraph))
            points.append(f"{sentence}{note.group(0)}" if note else sentence)
    flush()


def _chunk_company(doc: Document) -> None:
    lines = [line.strip() for line in doc.text.split("\n") if line.strip()]
    if not lines:
        return
    groups: list[tuple[str, list[str]]] = [(f"{doc.title}, вводная часть", [])]
    for line in lines:
        match = CLAUSE_RE.match(line)
        if match:
            groups.append((f"{doc.title}, п. {match.group(1)}", [line]))
        else:
            groups[-1][1].append(line)
    for label, paras in groups:
        if paras:
            for piece in _split_long("\n".join(paras)):
                doc.chunks.append(Chunk(doc.doc_id, label, piece))


def _company_title(name: str) -> str:
    stem = PurePosixPath(name).stem
    return stem.split("__", 1)[1] if "__" in stem else stem


def load_documents(path) -> list[Document]:
    documents: list[Document] = []
    total_dropped = 0
    for name, text in read_archive(path):
        clean, dropped = sanitize(text)
        total_dropped += dropped
        doc_id = _doc_id(name)
        if _is_law(name, clean):
            header, paragraphs, changes = _law_paragraphs(clean)
            source = header.get("Источник", "")
            short = _law_short_name(source, _company_title(name))
            doc = Document(doc_id, "law", source or short, "\n".join(paragraphs), short, source)
            doc.exported = header.get("Дата выгрузки", "")
            doc.changes = changes
            _chunk_law(doc, paragraphs)
            if short == "НК РФ" and doc.articles:
                doc.topic = nk_topic(doc.articles[0])
            if not doc.chunks:
                doc.chunks.append(Chunk(doc_id, short, doc.text[:MAX_CHUNK_CHARS]))
        else:
            doc = Document(doc_id, "company", _company_title(name), clean.strip())
            _chunk_company(doc)
        documents.append(doc)
    if not documents:
        raise ValueError("knowledge base has no readable documents")
    if total_dropped:
        log(f"removed {total_dropped} instruction-like line(s) from documents")
    return documents


def catalog(documents: list[Document]) -> str:
    lines = []
    for doc in documents:
        if doc.kind == "company":
            lines.append(f"- {doc.title}")
    laws: dict[str, dict[str, str]] = {}
    for doc in documents:
        if doc.kind == "law":
            for article in doc.articles or ["(текст без статей)"]:
                laws.setdefault(doc.short_name, {})[article] = doc.topic

    def article_key(number: str) -> list[int]:
        return [int(part) if part.isdigit() else 0 for part in number.split(".")]

    for short, articles in laws.items():
        ordered = [
            f"{a} ({articles[a]})" if articles[a] else a
            for a in sorted(articles, key=article_key)
        ]
        lines.append(f"- {short}: ст. {', '.join(ordered)} (только действующая редакция)")
    return "\n".join(lines)
