import re
import json
import asyncio
from typing import AsyncGenerator
import httpx
import tiktoken
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from .config import settings
from .db import record_usage

proxy_router = APIRouter()

_enc = tiktoken.get_encoding("cl100k_base")
_content_re = re.compile(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _count(text: str) -> int:
    return len(_enc.encode(text or ""))


def _unescape(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw.encode().decode("unicode_escape", "ignore")


async def _compress(text: str) -> str:
    from llmlingua import PromptCompressor

    compressor = PromptCompressor(
        model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
        use_llmlingua2=True,
        device_map="cpu",
    )
    out = await asyncio.to_thread(
        compressor.compress_prompt,
        text,
        rate=settings.TARGET_RATIO,
        force_tokens=["\n", ".", ",", "?", ":"],
    )
    return out["compressed_prompt"]


@proxy_router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    payload = await request.json()
    msgs = payload.get("messages", [])
    src = "\n".join(
        m.get("content", "")
        for m in msgs
        if m.get("content") and isinstance(m.get("content"), str)
    )
    raw_tokens = _count(src)
    compressed = await _compress(src) if src else ""

    if msgs and compressed:
        msgs[-1]["content"] = compressed
        payload["messages"] = msgs

    opt_tokens = _count(compressed)

    async def _gen() -> AsyncGenerator[bytes, None]:
        parts: list[str] = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as cl:
            async with cl.stream(
                "POST",
                f"{settings.UPSTREAM_BASE}/v1/chat/completions",
                json={**payload, "stream": True},
                headers={
                    "Authorization": request.headers.get("authorization", ""),
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

        gen_tokens = _count("".join(parts))
        delta = max(raw_tokens - opt_tokens, 0)
        await record_usage(
            model=payload.get("model", "unknown"),
            input_raw=raw_tokens,
            input_opt=opt_tokens,
            output=gen_tokens,
            cost_saved=(delta / 1000.0) * settings.RATE_PER_1K,
            orig_prompt=src,
            opt_prompt=compressed,
        )

    return StreamingResponse(_gen(), media_type="text/event-stream")
