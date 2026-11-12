from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path


CLAUSE = re.compile(r"^\s*(\d+(?:\.\d+)+)\.\s+")
SECTION = re.compile(r"^\s*(\d+)\.\s+")
ARTICLE = re.compile(r"^\s*(Статья\s+\d+(?:\.\d+)?)\.\s*", re.IGNORECASE)
LAW_POINT = re.compile(r"^\s*(\d+(?:\.\d+)*)([.)])\s+")


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_id: str
    source_path: str
    title: str
    source_type: str
    locator: str | None
    section: str | None
    text: str
    start_char: int
    end_char: int


def _line_offsets(text: str):
    offset = 0
    for line in text.splitlines(keepends=True):
        yield offset, line.rstrip("\r\n")
        offset += len(line)


def _split_span(text: str, start: int, end: int, max_chars: int, overlap: int):
    while end - start > max_chars:
        limit = start + max_chars
        floor = start + max_chars // 2
        cut = None
        for boundary in ("\n\n", "\n", ". ", " "):
            position = text.rfind(boundary, floor, limit)
            if position >= floor:
                cut = position + len(boundary)
                break
        cut = cut or limit
        yield start, cut
        start = max(start + 1, cut - overlap)
    if text[start:end].strip():
        yield start, end


def parse_txt(
    source_path: str,
    text: str,
    *,
    max_chars: int = 1600,
    overlap_chars: int = 160,
) -> list[TextChunk]:
    if max_chars < 200 or not 0 <= overlap_chars < max_chars // 2:
        raise ValueError("Invalid chunk size or overlap")
    if not text.strip():
        return []

    source_type = "law" if source_path.startswith("законы__") else "company"
    title = next((line.strip() for line in text.splitlines() if line.strip()), source_path)
    markers: list[tuple[int, str | None, str | None]] = []
    current_section: str | None = None
    current_article: str | None = None

    for offset, line in _line_offsets(text):
        if source_type == "law":
            if match := ARTICLE.match(line):
                current_article = match.group(1)
                markers.append((offset, current_article, None))
            elif current_article and (match := LAW_POINT.match(line)):
                kind = "п." if match.group(2) == "." else "подп."
                markers.append(
                    (offset, f"{current_article}, {kind} {match.group(1)}", None)
                )
            continue
        if match := CLAUSE.match(line):
            markers.append((offset, f"п. {match.group(1)}", current_section))
        elif match := SECTION.match(line):
            current_section = line.strip()
            markers.append((offset, f"разд. {match.group(1)}", current_section))

    spans: list[tuple[int, int, str | None, str | None]] = []
    if markers:
        if markers[0][0] > 0:
            spans.append((0, markers[0][0], None, None))
        for index, (start, locator, section) in enumerate(markers):
            end = markers[index + 1][0] if index + 1 < len(markers) else len(text)
            spans.append((start, end, locator, section))
    else:
        spans.append((0, len(text), None, None))

    chunks: list[TextChunk] = []
    for start, end, locator, section in spans:
        for piece_start, piece_end in _split_span(
            text, start, end, max_chars, overlap_chars
        ):
            if not text[piece_start:piece_end].strip():
                continue
            digest = hashlib.sha256(
                f"{source_path}\0{piece_start}\0{piece_end}".encode("utf-8")
            ).hexdigest()[:16]
            chunks.append(
                TextChunk(
                    chunk_id=digest,
                    source_path=source_path,
                    title=title,
                    source_type=source_type,
                    locator=locator,
                    section=section,
                    text=text[piece_start:piece_end],
                    start_char=piece_start,
                    end_char=piece_end,
                )
            )
    return chunks


def parse_txt_zip(path: str | Path, **chunk_options: int) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.lower().endswith(".txt") or name.startswith("__MACOSX/"):
                continue
            text = archive.read(name).decode("utf-8-sig")
            chunks.extend(parse_txt(name, text, **chunk_options))
    return chunks
