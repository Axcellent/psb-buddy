from typing import Literal
from pydantic import BaseModel, Field, field_validator


class RawChunkDto(BaseModel):
    id: str
    page: int | None = None
    text: str


class SourceReadDto(BaseModel):
    id: str
    title: str
    section: str | None = None
    page: int | None = None
    location: str | None = None

    pdf_url: str | None = Field(default=None, alias="pdfUrl")
    mime_type: str | None = Field(default=None, alias="mimeType")
    quote: str | None = None
    chunks: list[RawChunkDto] = Field(default_factory=list)
    chunk_id: str | None = Field(default=None, alias="chunkId")

    model_config = {"populate_by_name": True}


class MessageReadDto(BaseModel):
    id: str
    role: str
    time: str
    text: str
    sources: list[SourceReadDto] = Field(default_factory=list)


class MessageCreateDto(BaseModel):
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message is empty")
        return value


class ChatReadDto(BaseModel):
    id: str
    title: str
    date: str


class ChatCreateDto(BaseModel):
    title: str = "Новый диалог"


class RawSourceDto(BaseModel):
    doc_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    location: str | None = None
    section: str | None = None
    page: int | None = None
    quote: str | None = None
    chunks: list[RawChunkDto] = Field(default_factory=list)


class ContextMessageDto(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class RagResultDto(BaseModel):
    text: str = Field(min_length=1)
    sources: list[RawSourceDto] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("LLM answer is empty")
        return value
