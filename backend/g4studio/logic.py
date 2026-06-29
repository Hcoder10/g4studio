"""Gameplay-logic reviewer: the code compiles and the modules connect — this checks the
GAMEPLAY actually works end-to-end and is complete for the requested game. One reviewer
traces the core loops over every module, flags logic gaps, and full-context fixers repair.
"""
from __future__ import annotations

import asyncio

from .authored import _force_fix, _strip_fences
from .cerebras import CerebrasClient
from .genre_common import emit_ev, post_channel

LOGIC_REVIEW_SYSTEM = r"""You are the gameplay lead reviewing a COMPLETE Roblox game (you see every
module). The code already compiles and the modules already connect — your ONLY job is whether the
GAMEPLAY LOGIC actually works end-to-end and is COMPLETE for the requested game. Trace the core
loops and find real logic bugs/gaps:
- WIN and LOSE: is there code that actually DETECTS and FIRES both a victory and a defeat? A game
  with no way to win, or no way to lose, is broken — flag it.
- The core REWARD/PROGRESSION loop must close: the player's main action produces its effect AND its
  reward, and progress advances — e.g. killing an enemy removes it AND awards currency; spending
  currency actually produces the thing; clearing a wave/round advances to the next; score updates
  the win check.
- Entities/among are cleaned up (dead enemies removed, finished objects destroyed) and every loop
  terminates or yields.
- The objective from the REQUEST is actually achievable and the game ENDS with clear feedback.
- Nothing silently does nothing (a value updated but never used to drive an outcome).
List FIXES: each module needing a logic change, the concrete problem, and a precise instruction.
Only flag REAL gaps — if a loop already works, leave it."""

LOGIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fixes"],
    "properties": {
        "fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["module", "problem", "instruction"],
                "properties": {
                    "module": {"type": "string"},
                    "problem": {"type": "string"},
                    "instruction": {"type": "string"},
                },
            },
        },
    },
}

LOGIC_FIX_SYSTEM = r"""You are fixing the GAMEPLAY LOGIC of one module so the whole game works
end-to-end. Apply the fix precisely. Keep all features AND the existing integration conventions the
other modules rely on (the shared attributes / CollectionService tags / RemoteEvents — you can see
them). Only REAL Roblox API. Output ONLY the corrected Luau module."""


def _loc(m: dict) -> str:
    if m["kind"] == "shared":
        return f"ReplicatedStorage.G4Shared.{m['name']}"
    return f"ReplicatedStorage.G4Systems.{m['name']} (runs: {m['kind']})"


def _short(name: str) -> str:
    """Normalize a reviewer-provided module name (which may be a full path) to the short key."""
    return (name or "").split(".")[-1].split("/")[-1].split(" ")[0].strip()


async def run_logic_qa(prompt: str, spec: dict, modules: list[dict], client: CerebrasClient,
                       on_event=None) -> list[dict]:
    blob = "\n\n".join(f"-- ===== {_loc(m)} =====\n{m['source']}" for m in modules)
    emit_ev(on_event, "agent", id="logic", role="QA", name="Gameplay Logic", status="working")
    review, _ = await client.structured(
        LOGIC_REVIEW_SYSTEM,
        f"REQUESTED GAME: {prompt}\nFLOW: {spec.get('flow')}\n\nALL MODULES:\n{blob}",
        LOGIC_SCHEMA, name="logic_review", max_tokens=3500, temperature=0.3)
    fixes = [f for f in review.get("fixes", []) if f.get("module")]
    emit_ev(on_event, "agent", id="logic", status="done", detail=f"{len(fixes)} logic fix(es)")
    if fixes:
        post_channel(on_event, "logic", "Gameplay Logic", "Traced the core loops — found "
                     f"{len(fixes)} gap(s): " + " ".join(f"@{_short(f['module'])}" for f in fixes[:5])
                     + " please fix.")
    else:
        post_channel(on_event, "logic", "Gameplay Logic", "Traced the core loops — win/lose, rewards and progression all fire ✅")
    if not fixes:
        return modules

    by_name = {m["name"]: m for m in modules}

    async def fix_one(f: dict):
        m = by_name.get(_short(f["module"]))
        if not m:
            return None
        aid = f"logic:{m['name']}"
        emit_ev(on_event, "agent", id=aid, role="Coder", name=f["module"], status="working")
        user = (f"REQUESTED GAME: {prompt}\n\nEVERY MODULE (for context — keep shared names "
                f"consistent):\n{blob}\n\nMODULE TO FIX: {_loc(m)}\nPROBLEM: {f['problem']}\n"
                f"FIX INSTRUCTION: {f['instruction']}\n\nOutput the corrected '{m['name']}' module.")
        t = await client.chat([{"role": "system", "content": LOGIC_FIX_SYSTEM},
                               {"role": "user", "content": user}], max_tokens=12000, temperature=0.4)
        emit_ev(on_event, "agent", id=aid, status="done", detail="logic-fixed")
        return f["module"], _force_fix(_strip_fences(t.text or ""))

    for r in await asyncio.gather(*[fix_one(f) for f in fixes], return_exceptions=True):
        if isinstance(r, tuple) and len(r[1]) > 100:
            by_name[r[0]]["source"] = r[1]
    return modules
