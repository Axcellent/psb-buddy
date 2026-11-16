from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from services import MessageService
from schemas import (MessageCreateDto, MessageReadDto)

router = APIRouter(prefix="/api/chats/{chat_id}/messages", tags=["messages"])

@router.get("", response_model=list[MessageReadDto])
async def list_messages(chat_id: str, db: AsyncSession = Depends(get_db)):
    return await MessageService(db).list(chat_id)

@router.post("", response_model=MessageReadDto)
async def send_message(chat_id: str, body: MessageCreateDto, db: AsyncSession = Depends(get_db)):
    try:
        return await MessageService(db).send(chat_id, body.text)
    except ValueError as e:
        raise HTTPException(404, str(e))