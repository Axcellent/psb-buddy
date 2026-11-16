import os
import httpx
from schemas import RawSourceDto, ContextMessageDto, RagResultDto, RawChunkDto

LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:8001")
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT_SECONDS", "180.0"))

async def rag_answer(
    question: str,
    history: list[ContextMessageDto],
) -> RagResultDto:
    async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
        try:
            response = await client.post(
                f"{LLM_SERVICE_URL}/answer",
                json={
                    "question": question,
                    "history": [{"role": m.role, "content": m.content} for m in history],
                },
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            raise RuntimeError(f"LLM service error: {e}") from e

        sources = []
        for s in data.get("sources", []):
            sources.append(RawSourceDto(
                doc_id=s.get("doc_id", ""),
                chunk_id=s.get("chunk_id", ""),
                location=s.get("location"),
                section=s.get("section"),
                page=s.get("page"),
                quote=s.get("quote"),
                chunks=[
                    RawChunkDto(
                        id=c.get("id", ""),
                        page=c.get("page"),
                        text=c.get("text", ""),
                    )
                    for c in s.get("chunks", [])
                ],
            ))

        return RagResultDto(
            text=data.get("text", ""),
            sources=sources,
        )