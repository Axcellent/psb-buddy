from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Chat, Message, Document

class ChatRepo:
    def __init__(self, db: AsyncSession): 
        self.db = db

    async def list(self) -> list[Chat]:
        r = await self.db.execute(
            select(Chat)
            .order_by(Chat.updated_at.desc())
        )

        return list(r.scalars().all())

    async def get(self, chat_id: str) -> Chat | None:
        return await self.db.get(Chat, chat_id)

    async def create(self, title: str) -> Chat:
        c = Chat(title=title)

        self.db.add(c)
        await self.db.commit()

        await self.db.refresh(c)

        return c

    async def delete(self, chat_id: str) -> bool:
        c = await self.get(chat_id)

        if not c:
            return False
        await self.db.delete(c)
        await self.db.commit()

        return True

class MessageRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_chat(self, chat_id: str) -> list[Message]:
        r = await self.db.execute(
            select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(Message.created_at)
        )
        return list(r.scalars().all())

    async def create(
        self,
        chat_id: str,
        role: str,
        content: str,
        sources_json: str = "[]"
    ) -> Message:
        m = Message(
            chat_id=chat_id,
            role=role,
            content=content,
            sources_json=sources_json
        
        )
        self.db.add(m)
        await self.db.commit()

        await self.db.refresh(m)

        return m

class DocumentRepo:
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def get(self, doc_id: str) -> Document | None:
        return await self.db.get(Document, doc_id)