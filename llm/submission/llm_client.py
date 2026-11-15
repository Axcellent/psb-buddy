from __future__ import annotations

import re
import sys
import time
from typing import Any

import httpx

import config

RETRY_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
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


_state = {"deadline": None, "budget_floor": 0, "plain_budget": False, "rate_limited": 0}


def set_deadline(timestamp: float | None) -> None:
    _state["deadline"] = timestamp


def rate_limited() -> int:
    return _state["rate_limited"]


def time_left() -> float:
    deadline = _state["deadline"]
    return float("inf") if deadline is None else deadline - time.monotonic()


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
        remaining = time_left()
        if remaining < 2:
            raise LLMError(f"{path}: out of time")
        timeout = httpx.Timeout(min(config.REQUEST_TIMEOUT_SECONDS, remaining), connect=min(10.0, remaining))
        try:
            response = client.post(config.API_BASE + path, headers=headers, json=payload, timeout=timeout)
        except httpx.TransportError as exc:
            last_error = type(exc).__name__
            if is_last:
                break
            time.sleep(min(_delay(attempt, None), max(0.0, time_left() - 2)))
            continue
        if response.status_code == 429:
            _state["rate_limited"] += 1
        if response.status_code in RETRY_STATUSES and not is_last:
            last_error = f"HTTP {response.status_code}"
            time.sleep(min(_delay(attempt, response), max(0.0, time_left() - 2)))
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


def _complete(text: str) -> str:
    stripped = text.rstrip()
    if stripped.endswith((".", "!", "?", "»", ")", '"')):
        return stripped
    ends = [m.end() for m in re.finditer(r"[.!?»)](?=\s)", stripped)]
    if ends and ends[-1] > len(stripped) // 2:
        return stripped[: ends[-1]]
    return stripped


def chat(client: httpx.Client, messages: list[dict[str, str]], max_tokens: int | None = None) -> str:
    requested = max_tokens or config.MAX_TOKENS
    floor = 0 if _state["plain_budget"] else config.MIN_ANSWER_TOKENS
    budget = max(requested, _state["budget_floor"], floor)
    best = ""
    for attempt in range(3):
        try:
            body = post_json(client, "/chat/completions", config.API_KEY, {
                "model": config.LLM_MODEL,
                "messages": messages,
                "temperature": config.ANSWER_TEMPERATURE,
                "max_tokens": budget,
            })
        except LLMError as exc:
            if exc.status == 400 and "channel" in exc.detail.lower() and budget < 8192:
                budget = min(8192, budget * 2)
                continue
            if exc.status in (400, 422) and budget > requested and not _state["plain_budget"]:
                _state["plain_budget"] = True
                _state["budget_floor"] = 0
                budget = requested
                log(f"larger max_tokens rejected, using the configured value: {exc}")
                continue
            if best:
                break
            raise
        try:
            choice = body["choices"][0]
            text = _answer_text(choice["message"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("unexpected chat response shape") from exc
        reason = choice.get("finish_reason")
        if text and reason != "length":
            return text
        if len(text) > len(best):
            best = text
        if reason == "content_filter" or budget >= 8192 or _state["plain_budget"]:
            break
        budget = min(8192, budget * 2)
        _state["budget_floor"] = max(_state["budget_floor"], budget)
    if best:
        return _complete(best)
    raise LLMError("model returned an empty answer")


def rerank(client: httpx.Client, query: str, documents: list[str]) -> list[int]:
    if config.RERANKER_MODEL.lower().startswith("qwen3-reranker"):
        prefix = (
            '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. '
            'Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
        )
        suffix = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
        ranked = []
        for index, document in enumerate(documents):
            prompt = (
                prefix
                + '<Instruct>: Given a web search query, retrieve relevant passages that answer the query\n'
                + f'<Query>: {query}\n<Document>: {document}'
                + suffix
            )
            body = post_json(client, "/completions", config.RERANK_KEY, {
                "model": config.RERANKER_MODEL,
                "prompt": prompt,
                "max_tokens": 1,
                "temperature": 0,
            })
            try:
                answer = body["choices"][0]["text"].strip().lower()
            except (KeyError, IndexError, TypeError, AttributeError) as exc:
                raise LLMError("unexpected Qwen reranker response") from exc
            if answer not in ("yes", "no"):
                raise LLMError(f"unexpected Qwen reranker answer: {answer[:40]!r}")
            ranked.append((answer == "yes", index))
        return [index for _, index in sorted(ranked, key=lambda item: (-item[0], item[1]))]

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
