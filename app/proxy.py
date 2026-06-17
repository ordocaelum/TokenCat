import re
import json
import asyncio
import secrets
from typing import Any, AsyncGenerator
import httpx
import tiktoken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import settings
from .db import record_usage

proxy_router = APIRouter()

_security_auth = HTTPBearer()

_enc = tiktoken.get_encoding("cl100k_base")
_content_re = re.compile(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"')
_comment_re = re.compile(r"(#[^\n]*|//[^\n]*)")
_ws_re = re.compile(r"[ \t\r\n]+")

# Bidirectional schema maps: compress standard API keys to single-letter markers
KEY_MIN: dict[str, str] = {
    "messages": "M",
    "model": "m",
    "content": "c",
    "role": "r",
    "system": "s",
    "user": "u",
    "assistant": "a",
    "temperature": "t",
    "max_tokens": "x",
    "stream": "S",
    "functions": "F",
    "function_call": "f",
    "tools": "T",
    "tool_choice": "C",
    "top_p": "p",
    "frequency_penalty": "q",
    "presence_penalty": "P",
    "stop": "e",
    "n": "n",
}

KEY_MAX: dict[str, str] = {v: k for k, v in KEY_MIN.items()}


def minify_schema(payload: Any) -> Any:
    """Recursively compress standard API keys to single-letter markers."""
    if isinstance(payload, dict):
        return {KEY_MIN.get(k, k): minify_schema(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [minify_schema(item) for item in payload]
    return payload


def expand_schema(payload: Any) -> Any:
    """Reverse minified keys back to standard names."""
    if isinstance(payload, dict):
        return {KEY_MAX.get(k, k): expand_schema(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [expand_schema(item) for item in payload]
    return payload


def prune_struct(text: str) -> str:
    """Strip code comments and collapse multi-whitespace/newlines to single spaces."""
    text = _comment_re.sub("", text)
    text = _ws_re.sub(" ", text)
    return text.strip()


def _count(text: str) -> int:
    return len(_enc.encode(text or ""))


def _unescape(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw.encode().decode("unicode_escape", "ignore")


def _model_rate(model: str) -> float:
    """Return price per 1k tokens for the given model using MODEL_PRICING matrix."""
    pricing = settings.MODEL_PRICING
    for prefix, rate in pricing.items():
        if prefix != "default" and model.startswith(prefix):
            return rate
    return pricing.get("default", settings.RATE_PER_1K)


_compressor = None
_compressor_lock = asyncio.Lock()


async def _get_compressor():
    global _compressor
    if _compressor is None:
        async with _compressor_lock:
            if _compressor is None:
                from llmlingua import PromptCompressor

                _compressor = PromptCompressor(
                    model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
                    use_llmlingua2=True,
                    device_map="cpu",
                )
    return _compressor


async def _compress(text: str) -> str:
    if _count(text) <= 300:
        return text
    compressor = await _get_compressor()
    out = await asyncio.to_thread(
        compressor.compress_prompt,
        text,
        rate=settings.TARGET_RATIO,
        force_tokens=["\n", ".", ",", "?", ":"],
    )
    return out["compressed_prompt"]


@proxy_router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_security_auth),
):
    if not secrets.compare_digest(credentials.credentials, settings.GATEWAY_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized TokenCat Gateway Access")
    payload = await request.json()
    msgs = payload.get("messages", [])
    model = payload.get("model", "unknown")

    # Prune user/system content blocks before semantic compression
    pruned_msgs = []
    for m in msgs:
        role = m.get("role", "")
        content = m.get("content", "")
        if role in ("user", "system") and isinstance(content, str):
            content = prune_struct(content)
        pruned_msgs.append({**m, "content": content})

    src = "\n".join(
        m.get("content", "")
        for m in pruned_msgs
        if m.get("content") and isinstance(m.get("content"), str)
    )
    raw_tokens = _count(src)
    compressed = await _compress(src) if src else ""

    if pruned_msgs and compressed:
        pruned_msgs[-1]["content"] = compressed
        payload["messages"] = pruned_msgs

    opt_tokens = _count(compressed)
    rate = _model_rate(model)

    async def _gen() -> AsyncGenerator[bytes, None]:
        parts: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as cl:
                async with cl.stream(
                    "POST",
                    f"{settings.UPSTREAM_BASE}/v1/chat/completions",
                    json={**payload, "stream": True},
                    headers={
                        "Authorization": "Bearer " + settings.UPSTREAM_API_KEY,
                        "Content-Type": "application/json",
                    },
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            yield b"data: [DONE]\n\n"
                            break
                        for frag in _content_re.findall(data):
                            parts.append(_unescape(frag))
                        yield f"data: {data}\n\n".encode()
        finally:
            gen_tokens = _count("".join(parts))
            delta = max(raw_tokens - opt_tokens, 0)
            await record_usage(
                model=model,
                input_raw=raw_tokens,
                input_opt=opt_tokens,
                output=gen_tokens,
                cost_saved=(delta / 1000.0) * rate,
                orig_prompt=src,
                opt_prompt=compressed,
            )

    return StreamingResponse(_gen(), media_type="text/event-stream")
