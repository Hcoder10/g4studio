"""The Architect: turns ANY game request into a structured, buildable SPEC — the system
breakdown, the shared integration contract, per-system asset search-phrases, and the world.

This is the top of the segmented harness. It generalizes to any game (a simple game gets a
few systems; tower defense gets many). Downstream: resolve assets via the RAG, then a module
builder writes each system against the shared contract, then an integrator wires them.
"""
from __future__ import annotations

from .cerebras import CerebrasClient
from .genre_common import emit_ev

ARCHITECT_SYSTEM = r"""You are the lead game architect for an automated Roblox game studio.
Given a game request, design a precise, buildable spec via the tool. Decide the SYSTEMS this
SPECIFIC game needs — only what it needs. A simple game has 2-3 systems; a complex one (e.g.
tower defense) needs many: lobby, matchmaking, map/build, towers, enemies, waves, economy,
UI/HUD, VFX/audio.

For each system give:
- name
- run: where it runs — "server" (a Script in ServerScriptService), "client" (a LocalScript in
  StarterPlayerScripts), or "module" (a shared ModuleScript in ReplicatedStorage)
- responsibility: one or two sentences, concrete
- assets: short SEARCH PHRASES for assets it needs (e.g. "medieval stone tower",
  "zombie enemy model", "epic battle music", "explosion particle"); [] if none.

Define the SHARED CONTRACT every system relies on so independent engineers integrate cleanly:
- shared_remotes: RemoteEvent/RemoteFunction names (in ReplicatedStorage)
- shared_modules: shared ModuleScripts (name + purpose), e.g. a GameConfig module holding the
  tower/enemy/wave definition tables, a Remotes accessor.

Also: flow (e.g. "lobby -> matchmaking -> round -> results"), and world (the map/arena to build).
Be concrete and consistent. Prefer fewer, well-defined systems over many vague ones."""

ARCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "summary", "flow", "shared_remotes", "shared_modules", "systems", "world"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "flow": {"type": "string"},
        "shared_remotes": {"type": "array", "items": {"type": "string"}},
        "shared_modules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "purpose"],
                "properties": {"name": {"type": "string"}, "purpose": {"type": "string"}},
            },
        },
        "systems": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "run", "responsibility", "assets"],
                "properties": {
                    "name": {"type": "string"},
                    "run": {"type": "string", "enum": ["server", "client", "module"]},
                    "responsibility": {"type": "string"},
                    "assets": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "world": {"type": "string"},
    },
}


async def run_architect(prompt: str, client: CerebrasClient, on_event=None) -> tuple[dict, object]:
    emit_ev(on_event, "agent", id="architect", role="Architect", name="Architect", status="working")
    spec, turn = await client.structured(
        ARCHITECT_SYSTEM, prompt, ARCH_SCHEMA, name="game_spec", max_tokens=4000, temperature=0.5)
    n = len(spec.get("systems", []))
    emit_ev(on_event, "agent", id="architect", status="done",
            detail=f"{n} systems · {round(turn.tokens_per_sec)} tok/s")
    return spec, turn


def resolve_assets(spec: dict, k: int = 3) -> dict:
    """For every system's asset search-phrases, pull concrete asset candidates from the RAG."""
    try:
        from .rag.store import get_store
        store = get_store()
    except Exception:
        return {}
    resolved: dict = {}
    for sysd in spec.get("systems", []):
        for q in sysd.get("assets", []) or []:
            if q in resolved:
                continue
            hits = store.search(q, k=k)
            resolved[q] = [{"id": h["id"], "name": h["name"], "type": h["type"], "score": h["score"]}
                           for h in hits]
    return resolved
