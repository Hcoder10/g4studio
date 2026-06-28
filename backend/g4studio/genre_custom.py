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
from .assets import ASSET_NAMES, expand as expand_asset

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
                "key": {"type": "string"},                          # PascalCase folder name
                "role": {"type": "string"},                         # what it does in the game
                "asset": {"type": "string", "enum": ASSET_NAMES},   # prebuilt asset representing it
            },
            "required": ["key", "role", "asset"]}},
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

DESIGNER_SYSTEM = """You are the lead designer of an automated Roblox studio that builds ANY
kind of game from a prompt using a kit of PREBUILT ASSETS. Design a complete, fun, lively game.

The world is a BOUNDED ARENA ~120x120 studs centered on the origin (floor + perimeter walls are
added for you). Keep all coordinates within x,z in [-50, 50].

Output:
- `objects`: the catalog of object TYPES. Each has a `key` (ONE PascalCase word, e.g. "Coin",
  "Enemy", "Tree", "Goal"), a `role` (what it does), and an `asset` from the kit:
  GAMEPLAY assets (use for anything the rules touch): coin, gem, orb, button, flag, coin_pile.
  DECOR / STRUCTURE assets (for looks): tree, pine, rock, boulder, bush, crate, barrel, pillar,
  arch, torch, lamp, crystal, fence, tent, platform, wall, ramp.
  Pick the asset that best fits each object's role. Include SEVERAL decor object types so the
  arena feels alive (trees, rocks, torches, etc.).
- `areas`: regions of the arena. Each lists `contents` = which object keys to place and how many.
  Spread areas across the arena and pack them with decor.
- `spawn`: where players start (near origin).
- `mechanics`: PRECISE rules — what the player does, what each object type DOES, scoring, timing,
  win/lose. Reference object keys by name. Concrete enough to implement with no questions.
- `win`: the win/lose condition.
Make it a real, lively game with a clear objective and lots of decoration."""

AREA_SYSTEM = """You are a BUILDER placing prebuilt assets for ONE area of a Roblox arena. You only
choose POSITIONS (the asset art is placed for you). Given the area and the (object key, count) list,
output `placements`: an absolute world position for each instance, ON the floor (y near 0 — the
asset stacks upward itself).

Place things with a level designer's INTENT, for example:
- A row of 6 Trees along a path: x steps by ~9 each at the same z, e.g. (-22,0,12),(-13,0,12),(-4,0,12)...
- A ring of 8 Torches around center (0,0,0) radius ~16: points spaced around the circle.
- A cluster of Rocks: 4-5 positions within a ~10-stud blob.
- Collectibles in a trail or grid the player follows; the Goal at the far end.
Spread them out, avoid overlaps, stay inside the area (x,z within [-50,50]). Use the exact object keys."""

SCRIPTER_SYSTEM = """You are the GAMEPLAY PROGRAMMER for an automated Roblox studio. You write
the Luau SERVER SCRIPT that makes the game actually work.

THE CONTRACT (the world is already built for you):
- `local root = script.Parent` -- a Folder holding the whole game.
- Inside root is ONE Folder per object type, named EXACTLY by its key. Each folder holds
  BaseParts. e.g. root:FindFirstChild("Coin"):GetChildren() are the coin parts.
- A SpawnLocation named "Spawn" and a Folder "Arena" (floor + perimeter walls) already exist.
- Decorative folders (Tree, Rock, etc.) also exist; ignore them unless the rules use them.

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


async def _area_builder(client, idx, area, catalog, palette, on_event):
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
        asset = catalog.get(key, "crate")
        anchor = xyz(pl.get("pos"), (0, 0, 0))
        ops.extend(expand_asset(asset, key, f"{key}_a{idx}_{i + 1}", anchor, palette))
    emit_ev(on_event, "builder_done", stage=idx, name=name, counts={"objects": len(placements)}, ops=ops,
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


async def run_custom(prompt: str, client: CerebrasClient, on_event=None,
                     feedback=None) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    emit_ev(on_event, "director_started")
    designer_user = prompt if not feedback else \
        prompt + "\n\nREDESIGN FEEDBACK (the playtester rejected your last attempt — fix these): " + feedback
    design, dturn = await client.structured(DESIGNER_SYSTEM, designer_user, DESIGNER_SCHEMA,
                                            name="design", max_tokens=4000, temperature=0.6)
    turns = [dturn]
    name = design.get("name", "Custom Game")
    areas = design.get("areas") or []
    emit_ev(on_event, "director_done", name=name, theme=design.get("theme"), stages=len(areas),
            tokens=dturn.completion_tokens, tps=round(dturn.tokens_per_sec), ms=round(dturn.latency_ms))

    catalog = {_key(o.get("key")): str(o.get("asset", "crate")) for o in design.get("objects", [])}

    spawn = xyz(design.get("spawn"), (0, 4, 0))
    palette = [c for c in (design.get("palette") or []) if isinstance(c, str)] or ["#3a3f4b", "#6b7280"]
    AW = 120.0
    wall_c = palette[1] if len(palette) > 1 else "#6b7280"
    parts = [  # procedural bounded arena: floor + 4 perimeter walls + spawn
        op("Arena", "Floor", [0, 0, 0], [AW, 2, AW], palette[0], "Concrete"),
        op("Arena", "WallN", [0, 7, AW / 2], [AW, 14, 2], wall_c, "Concrete"),
        op("Arena", "WallS", [0, 7, -AW / 2], [AW, 14, 2], wall_c, "Concrete"),
        op("Arena", "WallE", [AW / 2, 7, 0], [2, 14, AW], wall_c, "Concrete"),
        op("Arena", "WallW", [-AW / 2, 7, 0], [2, 14, AW], wall_c, "Concrete"),
        op("_root", "Spawn", [spawn[0], 4, spawn[2]], (8, 1, 8), "#cfd8dc", "SmoothPlastic",
           klass="SpawnLocation"),
    ]
    emit_ev(on_event, "stage", ops=list(parts))

    # Scripter codes the game in parallel with the area builders (both need only the design).
    scripter_task = asyncio.create_task(_scripter(client, design, on_event))
    builder_results = await asyncio.gather(*[
        _area_builder(client, i, a, catalog, palette, on_event) for i, a in enumerate(areas)
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
