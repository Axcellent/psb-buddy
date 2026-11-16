import json
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from repos import ChatRepo, MessageRepo, DocumentRepo
from models import Chat, Message

from schemas import (ChatReadDto,
                     MessageReadDto,
                     SourceReadDto,
                     RagResultDto,
                     ContextMessageDto)

from rag import rag_answer

MONTHS_RU = ["янв.", "февр.", "мар.", "апр.", "мая", "июн.",
             "июл.", "авг.", "сент.", "окт.", "нояб.", "дек."]

WELCOME_TEXT = (
    "прив!"
)

def fmt_date(dt: datetime) -> str:
    return f"{dt.day} {MONTHS_RU[dt.month - 1]}"

def fmt_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def map_chat(c: Chat) -> ChatReadDto:
    return ChatReadDto(
        id=c.id,
        title=c.title,
        date=fmt_date(c.updated_at)
    )

def map_msg(m: Message) -> MessageReadDto:
    sources = [
        SourceReadDto(**s) for s in json.loads(m.sources_json or "[]")
    ]
    return MessageReadDto(
        id=m.id,
        role=m.role,
        time=fmt_time(m.created_at),
        text=m.content,
        sources=sources
    )


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ChatRepo(db)
        self.msg_repo = MessageRepo(db)

    async def list(self) -> list[ChatReadDto]:
        return [map_chat(c) for c in await self.repo.list()]

    async def create(self, title: str) -> ChatReadDto:
        chat = await self.repo.create(title)
        await self.msg_repo.create(chat.id, "assistant", WELCOME_TEXT, "[]")
        return map_chat(chat)

    async def delete(self, chat_id: str) -> bool:
        return await self.repo.delete(chat_id)


class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.chat_repo = ChatRepo(db)
        self.msg_repo = MessageRepo(db)
        self.doc_repo = DocumentRepo(db)

    async def list(self, chat_id: str) -> list[MessageReadDto]:
        return [map_msg(m) for m in await self.msg_repo.list_by_chat(chat_id)]

    async def send(self, chat_id: str, text: str) -> MessageReadDto:
        chat = await self.chat_repo.get(chat_id)
        if not chat:
            raise ValueError("chat not found")

        await self.msg_repo.create(chat_id, "user", text)
        
        history = await self.msg_repo.list_by_chat(chat_id)
        history_dto = [ContextMessageDto(role=m.role, content=m.content) for m in history]
        try:
            result = await rag_answer(text, history_dto)
        except Exception:
            result = RagResultDto(text="Не удалось получить ответ. Попробуйте ещё раз.", sources=[])

        sources: list[SourceReadDto] = []
        for s in result.sources:
            doc = await self.doc_repo.get(s.doc_id)
            sources.append(SourceReadDto(
                id=s.chunk_id,
                title=doc.title if doc else "Документ",
                section=s.section,
                page=s.page,
                location=s.location,
                pdfUrl=f"/api/documents/{s.doc_id}/file" if doc else None,
                quote=s.quote,
                chunks=s.chunks,
                chunkId=s.chunk_id,
            )
        )
            
        sources_json = json.dumps([x.model_dump() for x in sources], ensure_ascii=False)
        assistant = await self.msg_repo.create(chat_id, "assistant", result.text, sources_json)

        chat.updated_at = datetime.utcnow()
        await self.db.commit()

        return map_msg(assistant)