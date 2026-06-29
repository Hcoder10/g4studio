"""Final ship review: one executive-producer pass over the whole game for COMPLETENESS,
FUN/juice, BALANCE, and POLISH — then full-context fixers apply the few highest-impact changes.
"""
from __future__ import annotations

import asyncio

from .authored import _force_fix, _strip_fences
from .cerebras import CerebrasClient
from .genre_common import emit_ev, post_channel
from .logic import LOGIC_SCHEMA, _loc, _short

POLISH_REVIEW_SYSTEM = r"""You are the executive producer doing the FINAL SHIP review of a complete
Roblox game (you see every module). It compiles, the modules connect, and the core logic works.
Decide if it is a COMPLETE, POLISHED, FUN version of the requested game, and flag the few changes
that most increase fun & completeness:
- GAME FEEL / JUICE: key moments (action, hit, reward, wave/level change, win, lose) MISSING
  feedback — a Sound, a ParticleEmitter:Emit() burst, a TweenService pop/flash, floating
  damage/currency number popups (BillboardGui), a real victory/defeat screen with payoff.
- COMPLETENESS: anything the requested game obviously needs that is missing or only stubbed.
- BALANCE: numbers that make it trivial or impossible (cost vs income, enemy health vs damage,
  spawn rate, timers) — nudge toward a fair, escalating curve.
- POLISH: snapping UI that should tween; no visible objective/score; no clear success/failure feedback.
List FIXES: module + concrete problem + precise instruction. Only the changes that matter most;
if it is already complete and juicy, return no fixes."""

POLISH_FIX_SYSTEM = r"""You are polishing ONE module to make the game more COMPLETE and FUN (apply the
game-feel / completeness / balance fix described). Keep all features AND the integration conventions
the other modules rely on (shared attributes / CollectionService tags / RemoteEvents — you can see
them). Only REAL Roblox API. Output ONLY the corrected Luau module."""


async def run_polish_qa(prompt: str, spec: dict, modules: list[dict], client: CerebrasClient,
                        on_event=None) -> list[dict]:
    blob = "\n\n".join(f"-- ===== {_loc(m)} =====\n{m['source']}" for m in modules)
    emit_ev(on_event, "agent", id="polish", role="QA", name="Ship Review", status="working")
    review, _ = await client.structured(
        POLISH_REVIEW_SYSTEM,
        f"REQUESTED GAME: {prompt}\nFUN INTENT: {spec.get('fun', '')}\n"
        f"DIFFICULTY: {spec.get('difficulty', '')}\n\nALL MODULES:\n{blob}",
        LOGIC_SCHEMA, name="polish_review", max_tokens=3500, temperature=0.4)
    fixes = [f for f in review.get("fixes", []) if f.get("module")]
    emit_ev(on_event, "agent", id="polish", status="done", detail=f"{len(fixes)} polish fix(es)")
    if fixes:
        post_channel(on_event, "polish", "Ship Review", f"Final pass — {len(fixes)} completeness/"
                     "fun/balance fix(es): " + " ".join(f"@{_short(f['module'])}" for f in fixes[:5]))
    else:
        post_channel(on_event, "polish", "Ship Review", "Final pass — complete, balanced and juicy. Ready to ship ✅")
    if not fixes:
        return modules

    by_name = {m["name"]: m for m in modules}

    async def fix_one(f: dict):
        m = by_name.get(_short(f["module"]))
        if not m:
            return None
        aid = f"polish:{m['name']}"
        emit_ev(on_event, "agent", id=aid, role="Coder", name=f["module"], status="working")
        user = (f"REQUESTED GAME: {prompt}\n\nEVERY MODULE (keep shared names consistent):\n{blob}\n\n"
                f"MODULE TO POLISH: {_loc(m)}\nPROBLEM: {f['problem']}\nFIX: {f['instruction']}\n\n"
                f"Output the corrected '{m['name']}' module.")
        t = await client.chat([{"role": "system", "content": POLISH_FIX_SYSTEM},
                               {"role": "user", "content": user}], max_tokens=12000, temperature=0.45)
        emit_ev(on_event, "agent", id=aid, status="done", detail="polished")
        return f["module"], _force_fix(_strip_fences(t.text or ""))

    for r in await asyncio.gather(*[fix_one(f) for f in fixes], return_exceptions=True):
        if isinstance(r, tuple) and len(r[1]) > 100:
            by_name[r[0]]["source"] = r[1]
    return modules
