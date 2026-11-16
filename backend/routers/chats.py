from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from services import ChatService
from schemas import (ChatReadDto, ChatCreateDto)

router = APIRouter(prefix="/api/chats", tags=["chats"])

@router.get("", response_model=list[ChatReadDto])
async def list_chats(db: AsyncSession = Depends(get_db)):
    return await ChatService(db).list()

@router.post("", response_model=ChatReadDto)
async def create_chat(body: ChatCreateDto, db: AsyncSession = Depends(get_db)):
    return await ChatService(db).create(body.title)

@router.delete("/{chat_id}", status_code=204)
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    if not await ChatService(db).delete(chat_id):
        raise HTTPException(404, "chat not found")