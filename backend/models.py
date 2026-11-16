import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db import Base

def gen_id() -> str:
    return str(uuid.uuid4())

class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)

    title: Mapped[str] = mapped_column(String, default="Новый диалог")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at"
    )

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    chat_id: Mapped[str] = mapped_column(String, ForeignKey("chats.id", ondelete="CASCADE"), index=True)

    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chat: Mapped[Chat] = relationship(back_populates="messages")

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)

    title: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)

    mime: Mapped[str] = mapped_column(String, default="application/pdf")