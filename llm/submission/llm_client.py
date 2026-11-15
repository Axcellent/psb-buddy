from __future__ import annotations

import re
import sys
import time
from typing import Any

import httpx

import config

RETRY_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
MAX_RETRY_DELAY = 10.0
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(f"{message}: {detail}" if detail else message)
        self.status = status
        self.detail = detail


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def make_client() -> httpx.Client:
    workers = config.MAX_WORKERS
    return httpx.Client(
        timeout=httpx.Timeout(config.REQUEST_TIMEOUT_SECONDS, connect=10.0),
        limits=httpx.Limits(max_connections=workers + 2, max_keepalive_connections=workers + 2),
    )


def _delay(attempt: int, response: httpx.Response | None) -> float:
    if response is not None:
        try:
            return min(MAX_RETRY_DELAY, max(0.0, float(response.headers.get("retry-after", ""))))
        except ValueError:
            pass
    return min(MAX_RETRY_DELAY, 1.0 * 2**attempt)


def post_json(client: httpx.Client, path: str, key: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not config.API_BASE:
        raise LLMError("LLM_BASE_URL is not set")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    last_error = "no attempt"
    for attempt in range(MAX_ATTEMPTS):
        is_last = attempt == MAX_ATTEMPTS - 1
        try:
            response = client.post(config.API_BASE + path, headers=headers, json=payload)
        except httpx.TransportError as exc:
            last_error = type(exc).__name__
            if is_last:
                break
            time.sleep(_delay(attempt, None))
            continue
        if response.status_code in RETRY_STATUSES and not is_last:
            last_error = f"HTTP {response.status_code}"
            time.sleep(_delay(attempt, response))
            continue
        if response.status_code >= 400:
            detail = " ".join(response.text.split())[:200]
            raise LLMError(f"{path}: HTTP {response.status_code}", response.status_code, detail)
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError(f"{path}: response is not JSON") from exc
    raise LLMError(f"{path}: {last_error} after {MAX_ATTEMPTS} attempts")


def _answer_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    if not isinstance(content, str):
        return ""
    return THINK_BLOCK.sub("", content).strip()


def chat(client: httpx.Client, messages: list[dict[str, str]], max_tokens: int | None = None) -> str:
    budget = max_tokens or config.MAX_TOKENS
    for attempt in range(2):
        try:
            body = post_json(client, "/chat/completions", config.API_KEY, {
                "model": config.LLM_MODEL,
                "messages": messages,
                "temperature": config.TEMPERATURE,
                "max_tokens": budget,
            })
        except LLMError as exc:
            if attempt == 0 and exc.status == 400 and "channel" in exc.detail.lower():
                budget = min(8192, budget * 2)
                continue
            raise
        try:
            choice = body["choices"][0]
            text = _answer_text(choice["message"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("unexpected chat response shape") from exc
        if text:
            return text
        if choice.get("finish_reason") == "content_filter":
            break
        if choice.get("finish_reason") == "length":
            budget = min(8192, budget * 2)
    raise LLMError("model returned an empty answer")


def rerank(client: httpx.Client, query: str, documents: list[str]) -> list[int]:
    body = post_json(client, "/rerank", config.RERANK_KEY, {
        "model": config.RERANKER_MODEL,
        "query": query,
        "documents": documents,
        "top_n": len(documents),
    })
    try:
        items = body.get("results") or body.get("data") or []
        scored = [
            (float(item.get("relevance_score", item.get("score", 0.0))), position, int(item["index"]))
            for position, item in enumerate(items)
        ]
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise LLMError("unexpected rerank response shape") from exc
    has_scores = any(score != 0.0 for score, _, _ in scored)
    if has_scores:
        scored.sort(key=lambda entry: (-entry[0], entry[1]))
    order = []
    for _, _, index in scored:
        if 0 <= index < len(documents) and index not in order:
            order.append(index)
    if not order:
        raise LLMError("rerank returned no usable indices")
    return order


def embed(client: httpx.Client, texts: list[str], batch_size: int = 32) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        body = post_json(client, "/embeddings", config.EMBED_KEY, {
            "model": config.EMB_MODEL,
            "input": batch,
            "encoding_format": "float",
        })
        try:
            items = sorted(body["data"], key=lambda item: int(item.get("index", 0)))
            got = [[float(x) for x in item["embedding"]] for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMError("unexpected embeddings response shape") from exc
        if len(got) != len(batch):
            raise LLMError("embeddings count mismatch")
        vectors.extend(got)
    return vectors
