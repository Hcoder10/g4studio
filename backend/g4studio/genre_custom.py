"""General pipeline: design + CODE any game from a prompt (not a preset genre).

Designer  -> invents object types + a layout + natural-language game rules.
Builders  -> place the objects (parallel).
Scripter  -> WRITES the Luau gameplay Script against a fixed object contract,
             then a quick repair pass. This is what makes it adapt to anything.

Contract the Scripter codes against:
  - `root = script.Parent` is a Folder holding the whole game.
  - One Folder per object type (named by its key); each holds BaseParts.
  - A SpawnLocation "Spawn" and a "Ground" folder exist.
"""
from __future__ import annotations

import asyncio
import re
import time

from .cerebras import CerebrasClient
from .genre_common import VEC3, emit_ev, op, xyz

_HEX = {"type": "string"}

DESIGNER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "theme": {"type": "string"},
        "pitch": {"type": "string"},
        "palette": {"type": "array", "items": {"type": "string"}},
        "objects": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "key": {"type": "string"},      # PascalCase folder name
                "role": {"type": "string"},     # what it does in the game
                "color": _HEX,
                "material": {"type": "string"},
                "size": VEC3,
            },
            "required": ["key", "role", "color", "material", "size"]}},
        "areas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "center": VEC3, "size": VEC3,
                "contents": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"object": {"type": "string"}, "count": {"type": "number"}},
                    "required": ["object", "count"]}},
            },
            "required": ["name", "center", "size", "contents"]}},
        "spawn": VEC3,
        "mechanics": {"type": "string"},   # detailed rules for the scripter
        "win": {"type": "string"},
    },
    "required": ["name", "theme", "pitch", "palette", "objects", "areas", "spawn", "mechanics", "win"],
}

AREA_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"placements": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"object": {"type": "string"}, "pos": VEC3},
        "required": ["object", "pos"]}}},
    "required": ["placements"],
}

SCRIPT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"source": {"type": "string"}},
    "required": ["source"],
}

DESIGNER_SYSTEM = """You are the lead designer of an automated Roblox studio that can build
ANY kind of game from a prompt. Design a complete, fun, BUILDABLE game.

Output:
- `objects`: the catalog of object TYPES the world is made of. Each has a `key`
  (ONE PascalCase word, no spaces, e.g. "Coin", "Enemy", "Button", "Goal", "Platform",
  "Wall", "Lava"), a `role` (what it does in gameplay), color (hex), material, and size.
  Always include a walkable surface object (e.g. "Platform" or "Floor") unless the whole
  map is one ground plane.
- `areas`: regions of the map. Each lists `contents` = which object keys to place and how
  many. Builders will scatter them in the area. Spread areas around the spawn.
- `spawn`: where players start (on the ground, y a few studs up).
- `mechanics`: PRECISE rules describing exactly how the game plays — what the player does,
  what each object type DOES, scoring, timing, win/lose. Reference object keys by name.
  Be concrete enough that a programmer can implement it with no further questions.
- `win`: the win/lose condition.
Coordinates in studs, Y up. Colors hex. Make it a real, playable game."""

AREA_SYSTEM = """You are a BUILDER placing objects for ONE area of a Roblox map.
Given the area bounds and the list of (object key, count) to place, output `placements`:
for each object instance, an absolute world position INSIDE the area. Spread them sensibly
(surfaces/platforms low and walkable; collectibles slightly above surfaces; walls at edges).
Use the exact object keys given. Coordinates in studs."""

SCRIPTER_SYSTEM = """You are the GAMEPLAY PROGRAMMER for an automated Roblox studio. You write
the Luau SERVER SCRIPT that makes the game actually work.

THE CONTRACT (the world is already built for you):
- `local root = script.Parent` -- a Folder holding the whole game.
- Inside root is ONE Folder per object type, named EXACTLY by its key. Each folder holds
  BaseParts. e.g. root:FindFirstChild("Coin"):GetChildren() are the coin parts.
- A SpawnLocation named "Spawn" and a Folder "Ground" already exist under root.

REQUIREMENTS:
- Implement the MECHANICS and WIN CONDITION exactly, operating on those folders/parts.
- Services: game:GetService("Players"/"RunService"/"TweenService"/...).
- Scores: leaderstats (Folder "leaderstats" in the player holding IntValue stats).
- Collisions: part.Touched + Players:GetPlayerFromCharacter(hit.Parent). Clicking: add a
  ClickDetector to the part. Loops: task.spawn(function() while true do ... task.wait(t) end end)
  or RunService.Heartbeat. NEVER loop without a wait.
- Always handle players that join AND already-present players (Players.PlayerAdded + iterate
  Players:GetPlayers()). Guard with FindFirstChild / pcall. Never index a nil.
- Output ONLY valid Luau for ONE self-contained Script — real, working logic, no stubs."""

REPAIR_SYSTEM = """You review Luau for a Roblox Script and fix bugs WITHOUT changing the game:
nil indexing, wrong Roblox API names, missing nil checks, loops missing task.wait, wrong
service names. Keep the same gameplay. Output ONLY the corrected full Luau source."""


def _key(s: str) -> str:
    k = re.sub(r"[^A-Za-z0-9]", "", str(s)) or "Obj"
    return k[0].upper() + k[1:]


async def _area_builder(client, idx, area, catalog, on_event):
    name = area.get("name", f"Area {idx + 1}")
    emit_ev(on_event, "builder_started", stage=idx, name=name)
    contents = ", ".join(f"{c.get('count', 1)}x {_key(c.get('object'))}" for c in area.get("contents", []))
    user = (f"Area: {name}\nCenter: {area.get('center')}\nSize: {area.get('size')}\n"
            f"Place these: {contents}\nOutput placements now.")
    try:
        out, turn = await client.structured(AREA_SYSTEM, user, AREA_SCHEMA, name="area",
                                            max_tokens=5000, temperature=0.6)
    except Exception as e:
        emit_ev(on_event, "builder_error", stage=idx, error=str(e)[:200])
        return [], None
    placements = out.get("placements") or []
    ops = []
    for i, pl in enumerate(placements):
        key = _key(pl.get("object"))
        cat = catalog.get(key, {"color": "#9aa0a6", "material": "Neon", "size": [3, 3, 3]})
        ops.append(op(key, f"{key}_a{idx}_{i + 1}", pl.get("pos"), cat["size"], cat["color"], cat["material"]))
    emit_ev(on_event, "builder_done", stage=idx, name=name, counts={"objects": len(ops)}, ops=ops,
            tokens=turn.completion_tokens, tps=round(turn.tokens_per_sec), ms=round(turn.latency_ms))
    return ops, turn


async def _scripter(client, design, on_event):
    emit_ev(on_event, "agent", id="scripter", role="Coder", name="Scripter", status="working")
    catalog = "\n".join(f"- {_key(o.get('key'))}: {o.get('role', '')}" for o in design.get("objects", []))
    user = (f"Game: {design.get('name')}\nPitch: {design.get('pitch')}\nTheme: {design.get('theme')}\n\n"
            f"Object folders (key: role):\n{catalog}\n\n"
            f"MECHANICS:\n{design.get('mechanics')}\n\nWIN CONDITION:\n{design.get('win')}\n\n"
            "Write the complete Luau Script now.")
    out, turn = await client.structured(SCRIPTER_SYSTEM, user, SCRIPT_SCHEMA, name="script",
                                        max_tokens=7000, temperature=0.4)
    source = out.get("source") or ""
    turns = [turn]
    # one fast repair pass
    try:
        keys = ", ".join(_key(o.get("key")) for o in design.get("objects", []))
        rep_user = f"Folders under root: {keys}, Ground, Spawn.\n\nSCRIPT:\n{source}"
        rout, rturn = await client.structured(REPAIR_SYSTEM, rep_user, SCRIPT_SCHEMA,
                                              name="script", max_tokens=7000, temperature=0.2)
        if rout.get("source") and len(rout["source"]) > 40:
            source = rout["source"]
        turns.append(rturn)
    except Exception:
        pass
    emit_ev(on_event, "agent", id="scripter", status="done",
            detail=f"{len(source)} chars Luau · {round(turns[0].tokens_per_sec)} tok/s")
    return source, turns


async def run_custom(prompt: str, client: CerebrasClient, on_event=None) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    emit_ev(on_event, "director_started")
    design, dturn = await client.structured(DESIGNER_SYSTEM, prompt, DESIGNER_SCHEMA,
                                            name="design", max_tokens=4000, temperature=0.6)
    turns = [dturn]
    name = design.get("name", "Custom Game")
    areas = design.get("areas") or []
    emit_ev(on_event, "director_done", name=name, theme=design.get("theme"), stages=len(areas),
            tokens=dturn.completion_tokens, tps=round(dturn.tokens_per_sec), ms=round(dturn.latency_ms))

    catalog = {}
    for o in design.get("objects", []):
        catalog[_key(o.get("key"))] = {
            "color": o.get("color", "#9aa0a6"), "material": o.get("material", "SmoothPlastic"),
            "size": xyz(o.get("size"), (4, 1, 4)),
        }

    spawn = xyz(design.get("spawn"), (0, 4, 0))
    palette = design.get("palette") or ["#3a3f4b"]
    parts = [
        op("Ground", "Floor", [spawn[0], 0, spawn[2]], [220, 2, 220], palette[0], "Concrete"),
        op("_root", "Spawn", spawn, (8, 1, 8), "#cfd8dc", "SmoothPlastic", klass="SpawnLocation"),
    ]
    emit_ev(on_event, "stage", ops=list(parts))

    # Scripter codes the game in parallel with the area builders (both need only the design).
    scripter_task = asyncio.create_task(_scripter(client, design, on_event))
    builder_results = await asyncio.gather(*[
        _area_builder(client, i, a, catalog, on_event) for i, a in enumerate(areas)
    ])
    source, sturns = await scripter_task
    turns.extend(sturns)

    for ops, turn in builder_results:
        if turn is not None:
            turns.append(turn)
        parts.extend(ops)

    mechanics = f"--!nonstrict\n{source}\n"
    folders = sorted({p["folder"] for p in parts if p["folder"] != "_root"})
    build = {
        "root": "G4Game", "name": name, "folders": folders, "parts": parts,
        "scripts": [{"folder": "_root", "name": "G4Mechanics", "source": mechanics}],
    }
    wall_ms = (time.perf_counter() - t0) * 1000.0
    metrics = {
        "genre": "custom", "name": name, "pitch": design.get("pitch", ""),
        "agents": 1 + len(areas) + 1,  # designer + builders + scripter
        "wall_ms": round(wall_ms), "parts": len(parts),
        "completion_tokens": sum(t.completion_tokens for t in turns),
        "agent_tps": [round(t.tokens_per_sec) for t in turns],
        "object_types": len(catalog), "areas": len(areas),
    }
    emit_ev(on_event, "assembled", parts=len(parts), wall_ms=round(wall_ms))
    return build, metrics
