"""Play-test as a RUNTIME oracle. Instead of having an agent try to *play* well (which is
unreliable), we RUN the generated game in Studio Play Solo and capture real runtime ERRORS
(ScriptContext.Error / error-level logs). Those errors — nil indexing, attempt to call nil,
bad args — are exactly the logic bugs that compile + integration checks can't see. This module
maps each captured error to its module and repairs it with full-game context.
"""
from __future__ import annotations

import asyncio

from .authored import _force_fix, _strip_fences
from .cerebras import CerebrasClient
from .genre_common import emit_ev
from .lint import autofix

RUNTIME_FIX_SYSTEM = r"""You are fixing a RUNTIME ERROR that occurred while the game was actually
running in Roblox. You are given the exact error message (and stack), and every module for context.
Find the cause and fix the named module so the error cannot happen (guard nil values with
FindFirstChild/WaitForChild, fix bad argument types/counts, fix wrong API usage). Keep all features
AND the shared integration conventions (attributes / CollectionService tags / RemoteEvents the other
modules use). Only REAL Roblox API. Output ONLY the corrected Luau module."""


def _module_for(err: dict, names: set[str]) -> str | None:
    script = (err.get("script") or "")
    last = script.split(".")[-1].split("/")[-1]
    if last in names:
        return last
    hay = f"{err.get('script', '')} {err.get('message', '')} {err.get('trace', '')}"
    for n in names:
        if n and n in hay:
            return n
    return None


async def repair_runtime_errors(modules: list[dict], errors: list[dict],
                                client: CerebrasClient, on_event=None) -> list[dict]:
    if not errors:
        return []
    by_name = {m["name"]: m for m in modules}
    names = set(by_name)
    blob = "\n\n".join(f"-- ===== {m['name']} ({m['kind']}) =====\n{m['source']}" for m in modules)

    grouped: dict[str, list[dict]] = {}
    for e in errors:
        tgt = _module_for(e, names)
        if tgt:
            grouped.setdefault(tgt, []).append(e)
    if not grouped:  # errors we can't attribute -> give them all to every server module's review is overkill; skip
        return []

    emit_ev(on_event, "agent", id="runtime", role="QA", name="Runtime Oracle",
            status="done", detail=f"{len(errors)} runtime error(s) in {len(grouped)} module(s)")

    async def fix(name: str, errs: list[dict]):
        m = by_name.get(name)
        if not m:
            return None
        aid = f"runtime:{name}"
        emit_ev(on_event, "agent", id=aid, role="Coder", name=name, status="working")
        etext = "\n".join(f'- {e.get("message", "")}'
                          + (f'\n  at {e.get("trace", "")[:200]}' if e.get("trace") else "")
                          for e in errs[:6])
        user = (f"RUNTIME ERRORS while the game ran:\n{etext}\n\nEVERY MODULE (for context):\n{blob}\n\n"
                f"Fix the '{name}' module so these errors cannot happen. Output the corrected module.")
        t = await client.chat([{"role": "system", "content": RUNTIME_FIX_SYSTEM},
                               {"role": "user", "content": user}], max_tokens=12000, temperature=0.3)
        emit_ev(on_event, "agent", id=aid, status="done", detail="runtime-fixed")
        fixed = autofix(_force_fix(_strip_fences(t.text or "")))
        return {"name": name, "kind": m["kind"], "source": fixed} if len(fixed) > 100 else None

    out = [r for r in await asyncio.gather(*[fix(n, e) for n, e in grouped.items()]) if r]
    for fm in out:  # keep the in-memory cache current for the next round
        if fm["name"] in by_name:
            by_name[fm["name"]]["source"] = fm["source"]
    return out
