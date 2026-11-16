import asyncio, os, zipfile
from pathlib import Path, PurePosixPath

from db import SessionLocal, init_db
from models import Document
from config import DATA_DIR, DOCUMENTS_DIR

KB_NAMES = ("knowledge-base.zip", "kb.zip", "knowledge_base.zip")
DOC_SUFFIXES = {".txt", ".md", ".docx", ".pdf"}
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
}


def archive_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return info.filename
    raw = info.filename.encode("cp437", errors="replace")
    for encoding in ("utf-8", "cp866", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return info.filename


def unpack_knowledge_base(docs_dir: str) -> None:
    explicit = os.getenv("KB_PATH", "").strip()
    archive_path = Path(explicit) if explicit else next(
        (DATA_DIR / name for name in KB_NAMES if (DATA_DIR / name).is_file()), None
    )
    if archive_path is None:
        return
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            name = PurePosixPath(archive_name(info)).name
            if info.is_dir() or Path(name).suffix.lower() not in DOC_SUFFIXES:
                continue
            target = Path(docs_dir) / name
            if not target.exists():
                target.write_bytes(archive.read(info))


async def seed():
    await init_db()

    docs_dir = str(DOCUMENTS_DIR)
    os.makedirs(docs_dir, exist_ok=True)
    unpack_knowledge_base(docs_dir)

    async with SessionLocal() as db:
        for fname in os.listdir(docs_dir):
            path = os.path.join(docs_dir, fname)

            if not os.path.isfile(path):
                continue

            doc_id = fname.rsplit(".", 1)[0]

            if await db.get(Document, doc_id):
                continue

            mime = MIME_TYPES.get(Path(fname).suffix.lower(), "text/plain")

            db.add(
                Document(
                    id=doc_id,
                    title=fname,
                    path=fname,
                    mime=mime
                )
            )

        await db.commit()
        print("seeded")

if __name__ == "__main__":
    asyncio.run(seed())
