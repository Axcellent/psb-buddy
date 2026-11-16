import asyncio, os
from db import SessionLocal, init_db
from models import Document

async def seed():
    await init_db()

    docs_dir = os.getenv("DOCUMENTS_DIR", "./documents")
    os.makedirs(docs_dir, exist_ok=True)
    
    async with SessionLocal() as db:
        for fname in os.listdir(docs_dir):
            path = os.path.join(docs_dir, fname)

            if not os.path.isfile(path):
                continue

            doc_id = fname.rsplit(".", 1)[0]

            if await db.get(Document, doc_id):
                continue

            mime = "application/pdf" if fname.endswith(".pdf") else "text/plain"

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