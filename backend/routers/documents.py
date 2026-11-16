import asyncio
import io
import zipfile
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from repos import DocumentRepo
from config import DOCUMENTS_DIR

router = APIRouter(prefix="/api/documents", tags=["documents"])


def read_document_text(path) -> str:
    raw = path.read_bytes()
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        text = "\n".join(
            "".join(node.text or "" for node in paragraph.iter(ns + "t"))
            for paragraph in root.iter(ns + "p")
        )
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1251")
    return text.replace("\r\n", "\n").replace("\r", "\n")

async def document_path(doc_id: str, db: AsyncSession):
    doc = await DocumentRepo(db).get(doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    
    root = DOCUMENTS_DIR.resolve()
    path = (root / doc.path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "file not found on disk")
    return doc, path


@router.get("/{doc_id}")
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc, path = await document_path(doc_id, db)
    if path.suffix.lower() in {".txt", ".md", ".docx"}:
        try:
            text = await asyncio.to_thread(read_document_text, path)
        except (OSError, UnicodeError, zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            raise HTTPException(422, "document could not be read") from exc
        return {"id": doc.id, "title": doc.title, "text": text}
    return FileResponse(path, media_type=doc.mime, filename=doc.title, content_disposition_type="inline")


@router.get("/{doc_id}/file")
async def get_document_file(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc, path = await document_path(doc_id, db)
    return FileResponse(
        path,
        media_type=doc.mime,
        filename=doc.title
    )
