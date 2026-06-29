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
from .genre_simulator import run_simulator
from .genre_custom import run_custom
from .authored import run_authored

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

_SPINNER = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "pos": VEC3,
        "size": VEC3,  # a long thin bar, e.g. {x:16,y:1,z:1}
        "color": {"type": "string"},
        "axis": {"type": "string", "enum": ["x", "y", "z"]},  # rotation axis
        "speed": {"type": "number"},  # degrees / sec
    },
    "required": ["pos", "size", "color", "axis", "speed"],
}

_DECO = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"pos": VEC3, "size": VEC3, "color": {"type": "string"}},
    "required": ["pos", "size", "color"],
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
        "spinners": {"type": "array", "items": _SPINNER},
        "decorations": {"type": "array", "items": _DECO},
    },
    "required": ["platforms", "hazards", "checkpoints", "moving", "spinners", "decorations"],
}

# ---- prompts ---------------------------------------------------------------
DIRECTOR_SYSTEM = """You are the lead designer of an automated Roblox OBBY studio.
Given a player's prompt, design a complete, fun, PLAYABLE obstacle course as a
sequence of stages laid out along the +Z axis (Z increases toward the finish).

You MUST follow EVERY rule:
- Output BETWEEN 5 AND 7 stages. NEVER fewer than 5. Each stage is a distinct section
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
  zig-zag, spiral, rotating spinner blades. `mechanic` is a short build instruction for the builder.
- Make it feel like a real, polished game — stages should be rich, not bare.
- `palette`: 2-4 HEX colors (e.g. "#1de9b6") fitting the theme. Colors MUST be hex.

Example anchor progression (4 stages): start {x:0,y:4,z:0} -> {x:0,y:8,z:32} ->
{x:0,y:12,z:64} -> {x:0,y:16,z:96} -> end {x:0,y:18,z:128}."""

BUILDER_SYSTEM = """You are a BUILDER agent constructing ONE stage of a Roblox obby.
You are given the stage's start anchor, end anchor, mechanic, palette, and difficulty.
Fill the stage with parts the player can traverse from `start` to `end`.

Output strict JSON with six typed lists (platforms, hazards, checkpoints, moving, spinners, decorations):
- platforms: standing parts, typically ~8 x 1 x 8 studs. Place them so each is within a
  comfortable jump of the next (<= 12 studs apart horizontally, <= 5 studs rise).
- hazards: lava/kill bricks. Place them in the GAPS or BELOW the jump path so that
  FALLING means death — never block the only route with a hazard.
- checkpoints: if a checkpoint is requested, add ONE checkpoint platform near the stage end.
- moving: platforms that tween back and forth. Set axis ("x" or "z"), distance (10-20),
  speed (6-10). Use these only when the mechanic calls for it.

Rules:
- spinners: rotating kill-bars that sweep over a platform. Give pos (above a platform),
  size = a long thin bar like {x:16,y:1,z:1}, axis "y" (sweeps horizontally), speed 60-180.
  Use when the mechanic calls for spinning blades.
- decorations: NON-blocking themed visual props (pillars, crystals, arches, signs, lamps).
  Add 3-6 per stage BESIDE the path (never on it) to make the level feel like a real game,
  matching the theme and palette.

Rules:
- Use ABSOLUTE world coordinates in studs (not relative). Begin at `start`, end at `end`.
- All colors MUST be hex (e.g. "#4aa3ff"), drawn from the given palette.
- Aim for 6 to 10 platforms so the stage feels substantial.
- If the mechanic mentions moving platforms or spinners, you MUST output those entries.
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
    counts = {k: len(out.get(k, []) or []) for k in
              ("platforms", "hazards", "checkpoints", "moving", "spinners", "decorations")}
    _emit(cb, "builder_done", stage=idx, name=stage.get("name"), counts=counts,
          elements=out, tokens=turn.completion_tokens,
          tps=round(turn.tokens_per_sec), ms=round(turn.latency_ms))
    return out, turn


async def run_obby(prompt: str, client: CerebrasClient,
                   on_event: Optional[Callable] = None,
                   feedback: Optional[str] = None) -> tuple[dict, dict]:
    """Obby genre: prompt -> generic build dict + metrics. Emits streaming events."""
    t0 = time.perf_counter()
    turns: list[Turn] = []

    _emit(on_event, "director_started")
    director_user = (
        f"Player's request: {prompt}\n\n"
        "Design the obby now. At least 4 distinct stages, one continuous path, and honor "
        "every specific thing the player asked for (mechanics, moving platforms, checkpoints)."
    )
    if feedback:
        director_user += "\n\nREDESIGN FEEDBACK (the playtester rejected your last attempt — fix these): " + feedback
    MIN_STAGES = 5
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
        "spinners": [], "decorations": [],
    }
    for out, turn in results:
        if turn is not None:
            turns.append(turn)
        for k in ("platforms", "hazards", "checkpoints", "moving", "spinners", "decorations"):
            combined[k].extend(out.get(k, []) or [])

    if stages:
        combined["spawn"] = {"pos": _vget(stages[0].get("start"), (0, 4, 0))}
        combined["win"] = {"pos": _vget(stages[-1].get("end"), (0, 4, 120))}

    spec = spec_from_dict(combined)
    wall_ms = (time.perf_counter() - t0) * 1000.0
    metrics = {
        "genre": "obby",
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
        "spinners": len(spec.spinners),
        "decor": len(spec.decor),
        "spawn": combined.get("spawn", {}).get("pos"),
        "win": combined.get("win", {}).get("pos"),
    }
    _emit(on_event, "assembled", parts=spec.part_count(), wall_ms=round(wall_ms),
          spawn=metrics["spawn"], win=metrics["win"])
    from .emit import to_build
    build = to_build(spec)
    build["root"] = "G4Game"
    build["name"] = spec.name
    return build, metrics


# ---- genre routing ---------------------------------------------------------
GENRE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "genre": {"type": "string", "enum": ["obby", "simulator", "custom"]},
        "reason": {"type": "string"},
    },
    "required": ["genre", "reason"],
}

CLASSIFY_SYSTEM = """Classify the Roblox game the user wants into ONE category:
- "obby": an obstacle course / parkour — jumping across platforms, avoiding lava/hazards,
  reaching a finish (keywords: obby, parkour, jump, tower, climb, course).
- "simulator": walk around collecting things to earn currency and buy upgrades
  (keywords: simulator, collect, gather, farm, coins, pets, upgrade, grind).
- "custom": ANY OTHER kind of game — tycoon, PvP/battle, tag, racing, maze, clicker,
  survival, tower defense, hide-and-seek, king-of-the-hill, dropper, or any novel idea.
Choose "obby" or "simulator" ONLY for a clear, strong match; otherwise choose "custom"."""


async def classify_genre(client: CerebrasClient, prompt: str) -> str:
    try:
        out, _ = await client.structured(CLASSIFY_SYSTEM, prompt, GENRE_SCHEMA,
                                         name="genre", max_tokens=150, temperature=0.1)
        g = out.get("genre", "custom")
        return g if g in ("obby", "simulator", "custom") else "custom"
    except Exception:
        return "custom"


COMPLEXITY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "complexity": {"type": "string", "enum": ["simple", "complex"]},
        "reason": {"type": "string"},
    },
    "required": ["complexity", "reason"],
}

COMPLEXITY_SYSTEM = """Decide how to build a requested Roblox game:
- "complex": needs MULTIPLE coordinated systems — a lobby/menu, matchmaking, rounds or waves,
  an economy/shop, distinct subsystems that must talk (towers + enemies + UI), or multiplayer
  flow. Examples: tower defense; a round-based PvP arena with a shop; a tycoon with several
  systems; a battle royale; a simulator with pets + shop + zones + rebirth.
- "simple": one coherent scene with one main mechanic — an obby, a small collector, a parkour
  map, a basic clicker, a maze, a single-arena minigame.
Pick "complex" ONLY when several systems must coordinate; otherwise "simple"."""


async def classify_complexity(client: CerebrasClient, prompt: str) -> str:
    try:
        out, _ = await client.structured(COMPLEXITY_SYSTEM, prompt, COMPLEXITY_SCHEMA,
                                         name="route", max_tokens=150, temperature=0.0)
        c = out.get("complexity", "simple")
        return c if c in ("simple", "complex") else "simple"
    except Exception:
        return "simple"


GOOD_SCORE = 6        # playtester score that counts as "good enough"
MAX_REDESIGNS = 1     # one redesign attempt if rejected (bounds latency)


async def _dispatch(genre: str, prompt: str, client, on_event, feedback):
    if genre == "simulator":
        return await run_simulator(prompt, client, on_event, feedback)
    if genre == "custom":
        return await run_custom(prompt, client, on_event, feedback)
    return await run_obby(prompt, client, on_event, feedback)


async def generate_game(prompt: str, client: Optional[CerebrasClient] = None,
                        on_event: Optional[Callable] = None,
                        playtest: bool = True,
                        force_genre: Optional[str] = None) -> tuple[dict, dict]:
    """Classify -> build -> Playtester (vision) grades it. If the score is too low,
    the Playtester sends its critique back to the Designer, who redesigns with accurate
    instructions and the Builders rebuild — looping until good (or MAX_REDESIGNS).
    Returns (build_dict, metrics)."""
    own = client is None
    client = client or CerebrasClient()
    try:
        if force_genre in ("obby", "simulator", "custom", "segmented", "authored"):
            genre = force_genre
        else:
            # auto-route: multi-system games -> segmented harness; single-scene -> authored
            genre = "segmented" if await classify_complexity(client, prompt) == "complex" else "authored"
        _emit(on_event, "genre", genre=genre)

        if genre == "segmented":
            from .segmented import run_segmented
            return await run_segmented(prompt, client, on_event)
        if genre == "authored":
            return await run_authored(prompt, client, on_event)

        # --- preset genres (opt-in via force_genre) with the vision playtest loop ---
        from .playtester import run_playtest
        attempt, feedback, pt = 0, None, None
        build, metrics = {}, {}
        while True:
            build, metrics = await _dispatch(genre, prompt, client, on_event, feedback)
            if not playtest:
                return build, metrics
            build, pt = await run_playtest(client, build, genre, metrics.get("name", "game"), on_event)
            score = pt.get("score")
            if score is None or score >= GOOD_SCORE or attempt >= MAX_REDESIGNS:
                break
            attempt += 1
            feedback = (
                f"Your previous design scored {score}/10. The vision playtester found: "
                f"{'; '.join(pt.get('issues', []))}. Verdict: {pt.get('verdict', '')} "
                "Fix ALL of these. Build a clearly BOUNDED arena (a floor with perimeter WALLS), "
                "connect surfaces into a clear path, place objects DENSELY and on the surfaces "
                "(not scattered floating debris), and include an obvious goal/objective area.")
            _emit(on_event, "redesign", attempt=attempt, score=score, issues=pt.get("issues", []))
            _emit(on_event, "reset")

        metrics["playtest"] = pt
        metrics["attempts"] = attempt + 1
        metrics["agents"] = metrics.get("agents", 0) + 1  # the Playtester agent
        metrics["parts"] = len(build.get("parts", []))
        return build, metrics
    finally:
        if own:
            await client.aclose()
