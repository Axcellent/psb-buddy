from __future__ import annotations

import asyncio
import json
import os
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def first_env(*names: str, default: str = "") -> str:
    return next(
        (value for name in names if (value := os.getenv(name, "").strip())), default
    )


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int
    max_workers: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            base_url=first_env("LLM_BASE_URL", "OPENAI_BASE_URL").rstrip("/"),
            api_key=first_env("LLM_API_KEY", "OPENAI_API_KEY"),
            model=first_env(
                "LLM_MODEL", "OPENAI_MODEL", "GEN_MODEL", default="gpt-oss-20b"
            ),
            temperature=float(first_env("TEMPERATURE", default="0")),
            max_tokens=int(first_env("MAX_TOKENS", default="1024")),
            max_workers=max(1, int(first_env("MAX_WORKERS", default="2"))),
        )


settings = Settings.from_env()
if not settings.base_url.startswith(("http://", "https://")):
    raise RuntimeError("LLM_BASE_URL or OPENAI_BASE_URL must be an HTTP base URL")


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "developer", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)


class ChatResponse(BaseModel):
    answer: str
    model: str
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))
    app.state.semaphore = asyncio.Semaphore(settings.max_workers)
    try:
        yield
    finally:
        await app.state.client.aclose()


app = FastAPI(title="PSB LLM service", version="0.1.0", lifespan=lifespan)


def upstream_payload(request: ChatRequest, *, stream: bool) -> dict[str, Any]:
    return {
        "model": settings.model,
        "messages": [message.model_dump() for message in request.messages],
        "temperature": request.temperature
        if request.temperature is not None
        else settings.temperature,
        "max_tokens": request.max_tokens
        if request.max_tokens is not None
        else settings.max_tokens,
        "stream": stream,
    }


def upstream_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}


MAX_ATTEMPTS = 3
RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 8.0


def retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
    if response is not None:
        try:
            retry_after = float(response.headers.get("retry-after", ""))
            return min(RETRY_MAX_DELAY, max(0.0, retry_after))
        except ValueError:
            pass
    return min(RETRY_MAX_DELAY, RETRY_BASE_DELAY * 2**attempt)


async def send_chat_completion(
    payload: dict[str, Any], *, stream: bool
) -> httpx.Response:
    """POST /chat/completions, retrying transient failures a bounded number of times.

    The caller must check the status of the returned response and, when
    ``stream`` is true, close it.
    """
    client: httpx.AsyncClient = app.state.client
    for attempt in range(MAX_ATTEMPTS):
        is_last = attempt == MAX_ATTEMPTS - 1
        request = client.build_request(
            "POST",
            f"{settings.base_url}/chat/completions",
            headers=upstream_headers(),
            json=payload,
        )
        try:
            response = await client.send(request, stream=stream)
        except httpx.ReadTimeout:
            # The model already had the full read timeout; do not wait again.
            raise
        except httpx.TransportError:
            if is_last:
                raise
            await asyncio.sleep(retry_delay(attempt))
            continue
        if response.status_code in RETRY_STATUSES and not is_last:
            delay = retry_delay(attempt, response)
            await response.aclose()
            await asyncio.sleep(delay)
            continue
        return response
    raise AssertionError("unreachable")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    try:
        response = await app.state.client.get(
            f"{settings.base_url}/models", headers=upstream_headers(), timeout=5.0
        )
        response.raise_for_status()
        models = response.json()["data"]
        if not any(model.get("id") == settings.model for model in models):
            raise HTTPException(
                status_code=503, detail="Configured model is not available"
            )
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=503, detail="Model endpoint is unavailable"
        ) from exc
    return {"status": "ready", "model": settings.model}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    async with app.state.semaphore:
        try:
            response = await send_chat_completion(
                upstream_payload(request, stream=False), stream=False
            )
            response.raise_for_status()
            body = response.json()
            choice = body["choices"][0]
            answer = choice["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty model answer")
            return ChatResponse(
                answer=answer,
                model=body.get("model", settings.model),
                finish_reason=choice.get("finish_reason"),
                usage=body.get("usage"),
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504, detail="Model request timed out"
            ) from exc
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="Model request failed") from exc


@app.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        request = ChatRequest.model_validate(await websocket.receive_json())
    except WebSocketDisconnect:
        return
    except ValidationError, ValueError, TypeError:
        await websocket.send_json({"type": "error", "message": "Invalid chat request"})
        await websocket.close(code=1008)
        return

    try:
        async with (
            app.state.semaphore,
            aclosing(
                await send_chat_completion(
                    upstream_payload(request, stream=True), stream=True
                )
            ) as response,
        ):
            response.raise_for_status()
            await websocket.send_json({"type": "start", "model": settings.model})
            finish_reason = None
            received_content = False
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                if not data:
                    continue
                chunk = json.loads(data)
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        received_content = True
                        await websocket.send_json({"type": "delta", "content": content})
                    finish_reason = choice.get("finish_reason") or finish_reason
            if not received_content:
                raise ValueError("Empty model stream")
            await websocket.send_json({"type": "done", "finish_reason": finish_reason})
    except WebSocketDisconnect:
        return
    except httpx.TimeoutException:
        await websocket.send_json(
            {"type": "error", "message": "Model request timed out"}
        )
        await websocket.close(code=1011)
    except httpx.HTTPError, ValueError, KeyError, TypeError, IndexError:
        await websocket.send_json({"type": "error", "message": "Model request failed"})
        await websocket.close(code=1011)
