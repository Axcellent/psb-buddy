from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
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
            response = await app.state.client.post(
                f"{settings.base_url}/chat/completions",
                headers=upstream_headers(),
                json=upstream_payload(request, stream=False),
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
            app.state.client.stream(
                "POST",
                f"{settings.base_url}/chat/completions",
                headers=upstream_headers(),
                json=upstream_payload(request, stream=True),
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
