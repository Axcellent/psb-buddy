import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from repos import DocumentRepo

router = APIRouter(prefix="/api/documents", tags=["documents"])
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", "./documents")

@router.get("/{doc_id}")
async def get_document_file(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await DocumentRepo(db).get(doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    
    path = os.path.join(DOCUMENTS_DIR, doc.path)
    if not os.path.exists(path):
        raise HTTPException(404, "file not found on disk")
    
    return FileResponse(
        path,
        media_type=doc.mime,
        filename=doc.title
    )