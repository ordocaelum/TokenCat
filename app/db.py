import os
import asyncpg
from typing import Optional, Any

_pool: Optional[asyncpg.Pool] = None

_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS token_ledger (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ts timestamptz NOT NULL DEFAULT now(),
    model text,
    input_raw int,
    input_opt int,
    output int,
    cost_saved numeric(12,6),
    orig_prompt text,
    opt_prompt text
);
"""


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["SUPABASE_DB_DSN"],
            min_size=1,
            max_size=10,
        )
        async with _pool.acquire() as conn:
            await conn.execute(_SCHEMA)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _require_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool


async def record_usage(
    *,
    model: str,
    input_raw: int,
    input_opt: int,
    output: int,
    cost_saved: float,
    orig_prompt: str,
    opt_prompt: str,
) -> None:
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO token_ledger (model, input_raw, input_opt, output, cost_saved, orig_prompt, opt_prompt)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            model,
            input_raw,
            input_opt,
            output,
            cost_saved,
            orig_prompt,
            opt_prompt,
        )


async def fetch_kpis() -> dict[str, Any]:
    pool = _require_pool()
    async with pool.acquire() as conn:
        r = await conn.fetchrow(
            "SELECT COALESCE(SUM(input_raw), 0) AS raw, COALESCE(SUM(input_opt), 0) AS opt, COALESCE(SUM(cost_saved), 0) AS saved FROM token_ledger"
        )
    raw, opt, saved = int(r["raw"]), int(r["opt"]), float(r["saved"])
    comp_pct = round((1 - (opt / raw)) * 100, 2) if raw else 0.0
    return {"raw": raw, "opt": opt, "saved": saved, "comp_pct": comp_pct}


async def fetch_ledger(limit: int = 100) -> list[dict[str, Any]]:
    pool = _require_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ts AS created_at, orig_prompt AS orig, opt_prompt AS opt, input_raw AS raw_tokens, input_opt AS opt_tokens, cost_saved AS saved_fiat FROM token_ledger ORDER BY ts DESC LIMIT $1",
            limit,
        )
    return [dict(r) for r in rows]
