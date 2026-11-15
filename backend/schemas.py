from pydantic import BaseModel, Field
from typing import Literal

class SourceChunkDto(BaseModel):
    id: str
    page: int | None = None
    text: str

class SourceReadDto(BaseModel):
    id: str

    title: str
    section: str | None = None
    page: int | None = None

    pdf_url: str | None = Field(default=None, alias="pdfUrl")
    quote: str | None = None
    chunks: list[SourceChunkDto] = Field(default_factory=list)
    chunk_id: str | None = Field(default=None, alias="chunkId")

    model_config = {"populate_by_name": True}

class MessageReadDto(BaseModel):
    id: str
    role: str
    time: str
    text: str
    sources: list[SourceReadDto] = []

class MessageCreateDto(BaseModel):
    text: str

class ChatReadDto(BaseModel):
    id: str
    title: str
    date: str

class ChatCreateDto(BaseModel):
    title: str = "Новый диалог"


class RawSourceDto(BaseModel):
    doc_id: str
    chunk_id: str

    section: str | None = None
    page: int | None = None
    
    quote: str | None = None
    chunks: list[SourceChunkDto] = []

class ContextMessageDto(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class RagResultDto(BaseModel):
    text: str
    sources: list[RawSourceDto] = []