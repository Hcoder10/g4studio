"""The swarm: a Director designs the obby; parallel Builder agents fill each stage.

Because every Gemma-4 call returns in ~tens of ms on Cerebras, the Director plus
N stage-Builders (run concurrently) resolve a whole game in seconds. The Director
lays out a continuous corridor of stage anchors so Builders can run in parallel and
still connect end-to-end.

Structured output uses the forced-tool-call path (confirmed on Cerebras). Schemas
avoid minItems/maxItems (rejected by strict mode) and represent vectors as {x,y,z}.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional

from .cerebras import CerebrasClient, Turn
from .ops import GameSpec, spec_from_dict

# ---- schema fragments (strict-mode safe) ----------------------------------
VEC3 = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
    "required": ["x", "y", "z"],
}

_ELEM = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"pos": VEC3, "size": VEC3, "color": {"type": "string"}},
    "required": ["pos", "size", "color"],
}

_MOVING = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "pos": VEC3,
        "size": VEC3,
        "color": {"type": "string"},
        "axis": {"type": "string", "enum": ["x", "z"]},
        "distance": {"type": "number"},
        "speed": {"type": "number"},
    },
    "required": ["pos", "size", "color", "axis", "distance", "speed"],
}

DIRECTOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "theme": {"type": "string"},
        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
        "palette": {"type": "array", "items": {"type": "string"}},
        "stages": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "mechanic": {"type": "string"},
                    "start": VEC3,
                    "end": VEC3,
                    "checkpoint_at_end": {"type": "boolean"},
                },
                "required": ["name", "mechanic", "start", "end", "checkpoint_at_end"],
            },
        },
    },
    "required": ["name", "theme", "difficulty", "palette", "stages"],
}

BUILDER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "platforms": {"type": "array", "items": _ELEM},
        "hazards": {"type": "array", "items": _ELEM},
        "checkpoints": {"type": "array", "items": _ELEM},
        "moving": {"type": "array", "items": _MOVING},
    },
    "required": ["platforms", "hazards", "checkpoints", "moving"],
}

# ---- prompts ---------------------------------------------------------------
DIRECTOR_SYSTEM = """You are the lead designer of an automated Roblox OBBY studio.
Given a player's prompt, design a complete, fun, PLAYABLE obstacle course as a
sequence of stages laid out along the +Z axis (Z increases toward the finish).

You MUST follow EVERY rule:
- Output BETWEEN 4 AND 6 stages. NEVER fewer than 4. Each stage is a distinct section
  with its own mechanic and its own stretch of the path. A one-stage obby is unacceptable.
- Honor the player's SPECIFIC requests. If they mention moving platforms, make at least one
  stage's `mechanic` explicitly about moving platforms. If they mention N checkpoints, set
  `checkpoint_at_end` = true on at least N stages.
- Continuity: each stage's `start` MUST exactly equal the previous stage's `end`. The player
  SPAWNS at stage 1's `start` and WINS at the last stage's `end`.
- Reachability: between anchor points keep horizontal gaps <= 12 studs and vertical rise
  <= 5 studs (a character jumps ~7 high, ~16 across — keep it comfortable).
- Advance ~25-40 studs in +Z per stage and ascend gently overall. Y is up; units are studs.
- Vary mechanics across stages: rising steps, gaps over lava, moving platforms, narrow beams,
  zig-zag, spiral. `mechanic` is a short build instruction for the builder.
- `palette`: 2-4 HEX colors (e.g. "#1de9b6") fitting the theme. Colors MUST be hex.

Example anchor progression (4 stages): start {x:0,y:4,z:0} -> {x:0,y:8,z:32} ->
{x:0,y:12,z:64} -> {x:0,y:16,z:96} -> end {x:0,y:18,z:128}."""

BUILDER_SYSTEM = """You are a BUILDER agent constructing ONE stage of a Roblox obby.
You are given the stage's start anchor, end anchor, mechanic, palette, and difficulty.
Fill the stage with parts the player can traverse from `start` to `end`.

Output strict JSON with four typed lists (platforms, hazards, checkpoints, moving):
- platforms: standing parts, typically ~8 x 1 x 8 studs. Place them so each is within a
  comfortable jump of the next (<= 12 studs apart horizontally, <= 5 studs rise).
- hazards: lava/kill bricks. Place them in the GAPS or BELOW the jump path so that
  FALLING means death — never block the only route with a hazard.
- checkpoints: if a checkpoint is requested, add ONE checkpoint platform near the stage end.
- moving: platforms that tween back and forth. Set axis ("x" or "z"), distance (10-20),
  speed (6-10). Use these only when the mechanic calls for it.

Rules:
- Use ABSOLUTE world coordinates in studs (not relative). Begin at `start`, end at `end`.
- All colors MUST be hex (e.g. "#4aa3ff"), drawn from the given palette.
- Aim for 4 to 8 platforms so the stage feels substantial (more for longer stages).
- If the mechanic mentions moving platforms, you MUST output one or more `moving` entries.
- Keep it clean and beatable. Return empty lists for categories you don't use."""


def _vget(d: Any, default) -> dict:
    if isinstance(d, dict):
        return {"x": d.get("x", default[0]), "y": d.get("y", default[1]), "z": d.get("z", default[2])}
    return {"x": default[0], "y": default[1], "z": default[2]}


def _emit(cb: Optional[Callable], type_: str, **data) -> None:
    if cb:
        try:
            cb({"type": type_, **data})
        except Exception:
            pass


def _builder_user(stage: dict, palette: list, difficulty: str) -> str:
    return (
        f"Stage: {stage.get('name', 'stage')}\n"
        f"Mechanic: {stage.get('mechanic', 'simple platforms')}\n"
        f"Difficulty: {difficulty}\n"
        f"Start anchor: {stage.get('start')}\n"
        f"End anchor: {stage.get('end')}\n"
        f"Add checkpoint at end: {stage.get('checkpoint_at_end', True)}\n"
        f"Palette (use these hex colors): {', '.join(palette)}\n"
        f"Build this stage now."
    )


async def _run_builder(client: CerebrasClient, idx: int, stage: dict,
                       palette: list, difficulty: str, cb) -> tuple[dict, Optional[Turn]]:
    _emit(cb, "builder_started", stage=idx, name=stage.get("name"))
    try:
        out, turn = await client.structured(
            BUILDER_SYSTEM, _builder_user(stage, palette, difficulty),
            BUILDER_SCHEMA, name="stage_build", max_tokens=6000,
        )
    except Exception as e:  # one bad stage shouldn't kill the game
        _emit(cb, "builder_error", stage=idx, error=str(e)[:200])
        return {}, None
    counts = {k: len(out.get(k, []) or []) for k in ("platforms", "hazards", "checkpoints", "moving")}
    _emit(cb, "builder_done", stage=idx, name=stage.get("name"), counts=counts,
          elements=out, tokens=turn.completion_tokens,
          tps=round(turn.tokens_per_sec), ms=round(turn.latency_ms))
    return out, turn


async def generate_game(prompt: str, client: Optional[CerebrasClient] = None,
                        on_event: Optional[Callable] = None) -> tuple[GameSpec, dict]:
    """Prompt -> playable GameSpec. Emits events for the UI; returns (spec, metrics)."""
    own = client is None
    client = client or CerebrasClient()
    t0 = time.perf_counter()
    turns: list[Turn] = []

    _emit(on_event, "director_started")
    director_user = (
        f"Player's request: {prompt}\n\n"
        "Design the obby now. At least 4 distinct stages, one continuous path, and honor "
        "every specific thing the player asked for (mechanics, moving platforms, checkpoints)."
    )
    MIN_STAGES = 4
    spec_json, dturn = await client.structured(
        DIRECTOR_SYSTEM, director_user, DIRECTOR_SCHEMA, name="game_spec",
        max_tokens=4000, temperature=0.45)
    turns.append(dturn)
    stages = spec_json.get("stages") or []
    # The min-stage rule isn't always followed; a retry is ~400ms on Cerebras.
    retries = 0
    while len(stages) < MIN_STAGES and retries < 2:
        retries += 1
        nudge = director_user + (
            f"\n\nYour previous draft had only {len(stages)} stage(s) — REJECTED. Output at "
            "least 4 distinct stages with a continuous connected path. Try again.")
        spec_json, dturn = await client.structured(
            DIRECTOR_SYSTEM, nudge, DIRECTOR_SCHEMA, name="game_spec",
            max_tokens=4000, temperature=0.5)
        turns.append(dturn)
        stages = spec_json.get("stages") or []
    palette = [c for c in (spec_json.get("palette") or []) if isinstance(c, str)] or ["#9aa0a6"]
    difficulty = spec_json.get("difficulty", "medium")
    _emit(on_event, "director_done", name=spec_json.get("name"), theme=spec_json.get("theme"),
          stages=len(stages), tokens=dturn.completion_tokens,
          tps=round(dturn.tokens_per_sec), ms=round(dturn.latency_ms))

    # Builders run concurrently — the speed multiplier.
    results = await asyncio.gather(*[
        _run_builder(client, i, st, palette, difficulty, on_event) for i, st in enumerate(stages)
    ])

    combined: dict = {
        "name": spec_json.get("name", "G4 Obby"),
        "theme": spec_json.get("theme", ""),
        "difficulty": difficulty,
        "platforms": [], "hazards": [], "checkpoints": [], "moving": [],
    }
    for out, turn in results:
        if turn is not None:
            turns.append(turn)
        for k in ("platforms", "hazards", "checkpoints", "moving"):
            combined[k].extend(out.get(k, []) or [])

    if stages:
        combined["spawn"] = {"pos": _vget(stages[0].get("start"), (0, 4, 0))}
        combined["win"] = {"pos": _vget(stages[-1].get("end"), (0, 4, 120))}

    spec = spec_from_dict(combined)
    wall_ms = (time.perf_counter() - t0) * 1000.0
    metrics = {
        "name": spec.name,
        "agents": 1 + len(stages),
        "wall_ms": round(wall_ms),
        "completion_tokens": sum(t.completion_tokens for t in turns),
        "agent_tps": [round(t.tokens_per_sec) for t in turns],
        "parts": spec.part_count(),
        "platforms": len(spec.platforms),
        "hazards": len(spec.hazards),
        "checkpoints": len(spec.checkpoints),
        "moving": len(spec.moving),
        "spawn": combined.get("spawn", {}).get("pos"),
        "win": combined.get("win", {}).get("pos"),
    }
    _emit(on_event, "assembled", parts=spec.part_count(), wall_ms=round(wall_ms),
          spawn=metrics["spawn"], win=metrics["win"])
    if own:
        await client.aclose()
    return spec, metrics
