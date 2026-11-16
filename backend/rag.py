import httpx

from config import LLM_SERVICE_URL, AI_TIMEOUT
from schemas import ContextMessageDto, RagResultDto


class RagServiceError(RuntimeError):
    """LLM-сервис недоступен или нарушил контракт ответа."""

async def rag_answer(
    question: str,
    history: list[ContextMessageDto],
) -> RagResultDto:
    async with httpx.AsyncClient(timeout=httpx.Timeout(AI_TIMEOUT, connect=min(5.0, AI_TIMEOUT))) as client:
        try:
            response = await client.post(
                f"{LLM_SERVICE_URL}/answer",
                json={
                    "question": question,
                    "history": [{"role": m.role, "content": m.content} for m in history],
                },
            )
            response.raise_for_status()
            return RagResultDto.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise RagServiceError("LLM service request failed") from exc
