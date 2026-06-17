from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from html import escape
from .db import fetch_kpis, fetch_ledger

ux_router = APIRouter()


def _card(label: str, value: str, accent: str = "indigo", kpi_key: str = "") -> str:
    data_attr = f' data-kpi="{kpi_key}"' if kpi_key else ""
    return (
        f'<div class="bg-white rounded-2xl shadow-sm ring-1 ring-slate-200 p-6">'
        f'<p class="text-sm font-medium text-slate-500">{escape(label)}</p>'
        f'<p class="mt-2 text-3xl font-semibold text-{accent}-600"{data_attr}>{escape(value)}</p>'
        f"</div>"
    )


def _row(r: dict) -> str:
    ts = escape(str(r.get("created_at", "")))
    orig = escape((r.get("orig") or "")[:80])
    opt = escape((r.get("opt") or "")[:80])
    raw_t = r.get("raw_tokens", 0)
    opt_t = r.get("opt_tokens", 0)
    saved = float(r.get("saved_fiat") or 0)
    return (
        f'<tr class="border-t border-slate-100 hover:bg-slate-50">'
        f'<td class="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{ts}</td>'
        f'<td class="px-4 py-3 text-sm text-slate-600 max-w-xs truncate" title="{orig}">{orig}</td>'
        f'<td class="px-4 py-3 text-sm text-slate-600 max-w-xs truncate" title="{opt}">{opt}</td>'
        f'<td class="px-4 py-3 text-sm text-right tabular-nums">{raw_t}</td>'
        f'<td class="px-4 py-3 text-sm text-right tabular-nums text-indigo-600">{opt_t}</td>'
        f'<td class="px-4 py-3 text-sm text-right tabular-nums text-emerald-600">${saved:.4f}</td>'
        f"</tr>"
    )


def _page(kpis: dict, rows: list[dict]) -> str:
    cards = (
        _card("Raw Tokens", f"{kpis['raw']:,}", "slate", "raw")
        + _card("Optimized Tokens", f"{kpis['opt']:,}", "indigo", "opt")
        + _card("Compression", f"{kpis['comp_pct']}%", "violet", "comp_pct")
        + _card("Cost Saved", f"${kpis['saved']:.4f}", "emerald", "saved")
    )
    body = "".join(_row(r) for r in rows) or (
        '<tr><td colspan="6" class="px-4 py-8 text-center text-slate-400">No usage recorded.</td></tr>'
    )
    return (
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8"/>'
        '<meta name="viewport" content="width=device-width,initial-scale=1"/>'
        "<title>LLMLingua Proxy · Dashboard</title>"
        '<script src="https://cdn.tailwindcss.com"></script>'
        "</head>"
        '<body class="bg-slate-100 min-h-screen text-slate-900">'
        '<header class="bg-white border-b border-slate-200">'
        '<div class="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">'
        '<h1 class="text-xl font-bold tracking-tight">LLMLingua Proxy</h1>'
        '<span class="text-xs font-medium px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">live</span>'
        "</div>"
        "</header>"
        '<main class="max-w-7xl mx-auto px-6 py-8 space-y-8">'
        '<section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">'
        f"{cards}"
        "</section>"
        '<section class="bg-white rounded-2xl shadow-sm ring-1 ring-slate-200 overflow-hidden">'
        '<div class="px-6 py-4 border-b border-slate-100">'
        '<h2 class="text-sm font-semibold text-slate-700">Token Ledger</h2>'
        "</div>"
        '<div class="overflow-x-auto">'
        '<table class="min-w-full text-left">'
        '<thead class="bg-slate-50">'
        '<tr class="text-xs font-semibold uppercase tracking-wide text-slate-500">'
        '<th class="px-4 py-3">Time</th>'
        '<th class="px-4 py-3">Original</th>'
        '<th class="px-4 py-3">Optimized</th>'
        '<th class="px-4 py-3 text-right">Raw</th>'
        '<th class="px-4 py-3 text-right">Opt</th>'
        '<th class="px-4 py-3 text-right">Saved</th>'
        "</tr>"
        "</thead>"
        f'<tbody id="ledger-body">{body}</tbody>'
        "</table>"
        "</div>"
        "</section>"
        "</main>"
        "<script>"
        "function _fmt(n){return Number(n).toLocaleString();}"
        "function _pct(n){return Number(n).toFixed(2)+'%';}"
        "function _usd(n){return '$'+Number(n).toFixed(4);}"
        "function _esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}"
        "function refreshKpis(){"
        "  fetch('/api/kpis').then(function(r){return r.json();}).then(function(d){"
        "    var cards=document.querySelectorAll('[data-kpi]');"
        "    cards.forEach(function(el){"
        "      var k=el.getAttribute('data-kpi');"
        "      if(k==='raw')el.textContent=_fmt(d.raw);"
        "      else if(k==='opt')el.textContent=_fmt(d.opt);"
        "      else if(k==='comp_pct')el.textContent=_pct(d.comp_pct);"
        "      else if(k==='saved')el.textContent=_usd(d.saved);"
        "    });"
        "  }).catch(function(){});"
        "}"
        "function refreshLedger(){"
        "  fetch('/api/ledger').then(function(r){return r.json();}).then(function(rows){"
        "    var tbody=document.getElementById('ledger-body');"
        "    if(!tbody)return;"
        "    tbody.innerHTML=rows.length===0"
        "      ?'<tr><td colspan=\"6\" class=\"px-4 py-8 text-center text-slate-400\">No usage recorded.</td></tr>'"
        "      :rows.map(function(r){"
        "          var ts=_esc(String(r.created_at||''));"
        "          var orig=_esc((r.orig||'').substring(0,80));"
        "          var opt=_esc((r.opt||'').substring(0,80));"
        "          var saved=parseFloat(r.saved_fiat||0).toFixed(4);"
        "          return '<tr class=\"border-t border-slate-100 hover:bg-slate-50\">'"
        "            +'<td class=\"px-4 py-3 text-xs text-slate-400 whitespace-nowrap\">'+ts+'</td>'"
        "            +'<td class=\"px-4 py-3 text-sm text-slate-600 max-w-xs truncate\" title=\"'+orig+'\">'+orig+'</td>'"
        "            +'<td class=\"px-4 py-3 text-sm text-slate-600 max-w-xs truncate\" title=\"'+opt+'\">'+opt+'</td>'"
        "            +'<td class=\"px-4 py-3 text-sm text-right tabular-nums\">'+r.raw_tokens+'</td>'"
        "            +'<td class=\"px-4 py-3 text-sm text-right tabular-nums text-indigo-600\">'+r.opt_tokens+'</td>'"
        "            +'<td class=\"px-4 py-3 text-sm text-right tabular-nums text-emerald-600\">$'+saved+'</td>'"
        "            +'</tr>';"
        "        }).join('');"
        "  }).catch(function(){});"
        "}"
        "setInterval(refreshKpis,3000);"
        "setInterval(refreshLedger,3000);"
        "</script>"
        "</body>"
        "</html>"
    )


@ux_router.get("/", response_class=HTMLResponse)
@ux_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(_page(await fetch_kpis(), await fetch_ledger()))


@ux_router.get("/api/kpis")
async def api_kpis() -> JSONResponse:
    return JSONResponse(await fetch_kpis())


@ux_router.get("/api/ledger")
async def api_ledger() -> JSONResponse:
    return JSONResponse(await fetch_ledger(50))
