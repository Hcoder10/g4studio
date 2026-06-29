"""Integration QA: ONE reviewer sees EVERY module at once (they all fit in Gemma-4's
context) so it understands how the systems are supposed to connect, decides the canonical
CONVENTIONS the whole game must follow, and lists per-module fixes. Then focused fixers
rewrite each flagged module to conform.

This catches the bugs per-module builders can't: mismatched conventions (enemy tagging),
inconsistent remote payload shapes, duplicated state ownership (gold in two systems), dead
hooks / missing connections, contract violations.
"""
from __future__ import annotations

import asyncio

from .authored import _force_fix, _strip_fences
from .cerebras import CerebrasClient
from .genre_common import emit_ev

REVIEW_SYSTEM = r"""You are the INTEGRATION lead reviewing a COMPLETE multi-module Roblox game.
You can see EVERY module. Your job is to find the cross-module integration bugs that individual
engineers miss because each only saw their own piece:
- mismatched conventions (e.g. one system tags/locates enemies one way, another looks for them
  a different way) — so nothing finds anything;
- RemoteEvent payload shapes that differ between the SENDER and the RECEIVER (fields the
  receiver never reads, or values sent in a shape it ignores);
- duplicated or conflicting ownership of state (e.g. two systems each tracking & deducting gold);
- dead hooks / missing connections (a system exposes a function nobody calls, or needs something
  nobody provides — e.g. a UI shop button that can't reach the placement system);
- contract violations (raw remote paths, requiring another system module, wrong service).

CRITICAL CONSTRAINT: systems CANNOT require each other, so your conventions MUST use
contract-compatible mechanisms — NEVER "system A calls a function on system B". Use:
- Roblox ATTRIBUTES for shared state: per-player (player:SetAttribute("Gold", n) — it auto-
  replicates so the client HUD reads it directly via GetAttribute + GetAttributeChangedSignal,
  usually NO remote needed); global (workspace:SetAttribute("BaseHealth"/"CurrentWave"/"GameState")).
- CollectionService TAGS + attributes to represent/find game entities: tag enemies "Enemy", store
  per-entity Health/PathProgress as attributes, give each a PrimaryPart; find via GetTagged.
- the existing RemoteEvents only for explicit client<->server signals.

DECIDE the canonical CONVENTIONS the whole game will now follow — SPECIFIC and CONCRETE so each
engineer conforms without seeing the others. Cover at least: how enemies are tagged + where they
live + which attributes hold their Health/PathProgress + their PrimaryPart for position; which ONE
mechanism owns player gold (prefer player:SetAttribute("Gold")) and how systems spend/award it
WITHOUT cross-requiring; exactly how the client HUD reads gold/wave/health (prefer reading the
replicated attributes directly); and the single client tower-shop -> ghost -> click -> place path.
Implement everything by EDITING THE EXISTING modules — do NOT invent new infrastructure.

Then list FIXES: for every module that must change, the problem and a precise instruction to
conform. Only include modules that actually need changes."""

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["conventions", "fixes"],
    "properties": {
        "conventions": {"type": "string"},
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

FIX_SYSTEM = r"""You are fixing ONE module of a Roblox game to conform to the integration
CONVENTIONS the lead decided (given). Apply the fix instruction precisely and make this module
fully consistent with the conventions (enemy tagging/location, gold ownership + spend/award
mechanism, the exact UpdateHUD payload shape, the placement flow). Keep everything else about the
module working — do not remove features. Only REAL Roblox API. Output ONLY the corrected Luau
(a ModuleScript returning a table with start(), unless it was a shared data/util module)."""


def _loc(m: dict) -> str:
    if m["kind"] == "shared":
        return f"ReplicatedStorage.G4Shared.{m['name']}"
    return f"ReplicatedStorage.G4Systems.{m['name']} (runs: {m['kind']})"


async def run_integration_qa(spec: dict, modules: list[dict], client: CerebrasClient,
                             on_event=None) -> list[dict]:
    blob = "\n\n".join(f"-- ===== {_loc(m)} =====\n{m['source']}" for m in modules)
    remotes = ", ".join(spec.get("shared_remotes", []))

    emit_ev(on_event, "agent", id="integration", role="QA", name="Integration QA", status="working")
    review, _ = await client.structured(
        REVIEW_SYSTEM,
        f"SHARED REMOTES: {remotes}\nFLOW: {spec.get('flow')}\n\nALL MODULES:\n{blob}",
        REVIEW_SCHEMA, name="integration_review", max_tokens=4000, temperature=0.3)
    conventions = review.get("conventions", "")
    fixes = [f for f in review.get("fixes", []) if f.get("module")]
    emit_ev(on_event, "agent", id="integration", status="done",
            detail=f"{len(fixes)} integration fix(es)")
    if not conventions or not fixes:
        return modules

    by_name = {m["name"]: m for m in modules}

    async def fix_one(f: dict):
        m = by_name.get(f["module"])
        if not m:
            return None
        aid = f"fix:{f['module']}"
        emit_ev(on_event, "agent", id=aid, role="Coder", name=f["module"], status="working")
        user = (f"INTEGRATION CONVENTIONS (the whole game follows these):\n{conventions}\n\n"
                f"EVERY MODULE IN THE GAME (reconcile YOUR module against these — match exactly how "
                f"the OTHER modules tag/store/read the shared state you both touch):\n{blob}\n\n"
                f"MODULE TO FIX: {_loc(m)}\nPROBLEM: {f['problem']}\nFIX INSTRUCTION: {f['instruction']}\n\n"
                f"Output the corrected '{m['name']}' module (its current source is in the list above), "
                f"fully conforming to the conventions and consistent with the other modules.")
        t = await client.chat([{"role": "system", "content": FIX_SYSTEM},
                               {"role": "user", "content": user}], max_tokens=12000, temperature=0.4)
        emit_ev(on_event, "agent", id=aid, status="done", detail="integration-fixed")
        return f["module"], _force_fix(_strip_fences(t.text or ""))

    for r in await asyncio.gather(*[fix_one(f) for f in fixes]):
        if r and len(r[1]) > 100:
            by_name[r[0]]["source"] = r[1]
    return modules
