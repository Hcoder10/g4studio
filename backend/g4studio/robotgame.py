"""Gemma generates FUN robot-manipulation games that collect training data as you play.

The arm, IK, hover-control and trace recording are the fixed kit; Gemma only writes the Game module
(scene + rules + scoring + juice + per-step skill labels). A Director invents the game, a Coder
builds it against the ctx API, and we syntax-check the result.
"""
import asyncio
import os
import random

from .authored import _strip_fences
from .cerebras import CerebrasClient

CTX_API = r"""The arm + controls + per-step trace recording are PROVIDED. You only write the fun.
You get a `ctx` with:
- ctx.region : { center=Vector3, reach=number(~5.5), table=Part }. PUT EVERY OBJECT within `reach`
  studs of ctx.region.center, on the table (center.Y is the table top). Never place things behind
  or under the arm — only the forward workcell is reachable.
- ctx.state : a free table for your variables (cleared each round).
- ctx.t : seconds since this round started.
- ctx.arm : the SO-101 (arm.tip.Position = gripper tip; arm.grasped = held part or nil).
- ctx.holding() -> BasePart? : the part currently gripped.
- ctx.spawnCube(pos, color3?, size?) -> Part : a GRASPABLE cube.
- ctx.spawnBin(pos, color3?, size3?) -> Part : a static target/bin/zone.
- ctx.spawnPart({...}) -> Part : a custom anchored part. Use REAL Roblox Part property names in the
  table (Size=Vector3, Color=Color3.fromRGB(...) [NOT "Color3"], Material=Enum.Material..., Shape=
  Enum.PartType..., Transparency=n). NOT graspable unless ctx.makeGraspable(p). Prefer
  ctx.spawnCube / ctx.spawnBin whenever you can.
- ctx.makeGraspable(part).
- ctx.attachTool(props, offset?) -> Part : give the arm a tool to HOLD from the start (props = Part
  props {Size=Vector3, Color=Color3..., Shape=Enum.PartType...}; offset = CFrame of the tool below
  the gripper, e.g. CFrame.new(0,-1.3,0)). Returns the tool — track its .Position for dip / scoop /
  pour / stamp detection. This makes the EASIEST games (no grabbing required).
- EASY by default: prefer ONE held tool + ONE simple action; use generous distance thresholds
  (>= 2 studs); win fast. Avoid precise stacking / strict order unless asked.
- ctx.hud(text) : the big top text. Keep it SHORT and CRYSTAL CLEAR — say exactly what to do right
  now + progress, e.g. "Grab the RED block -> drop it in the RED bin   (2 left)". Call it in setup
  AND whenever the goal changes (next item, score, time).
- ctx.popup(pos, text, color3?) / ctx.burst(pos, color3?) / ctx.ding(good) : juice. Use them on
  EVERY success — make it satisfying.
- ctx.win(score) / ctx.lose() : end the round (ships the trace, auto-resets to a fresh round).
- ctx.dist(a,b), ctx.rand(lo,hi).

Return a ModuleScript table:
return {
    name = "<catchy name>",
    task = "<short_snake_case_id>",
    skill = "<robot skill it teaches>",
    setup = function(ctx) ... end,   -- build the scene + ctx.state + goal. Runs at the start of every round.
    step = function(ctx, dt) ... return reward, subgoal end,  -- every frame: scoring, juice, win/lose.
}
Each frame the harness AUTOMATICALLY records a trace step = (arm joint angles, the player's action,
your `reward`, your `subgoal`). So:
- reward (number): shape it densely — e.g. -ctx.dist(tip, goal) while reaching, +5 on a sub-success.
- subgoal (string): the skill phase happening RIGHT NOW — one of
  "reach" | "grasp" | "transport" | "place" | "sort" | "stack" | "insert" | "press" | "idle".
  This is the high-level label that makes the data useful."""

EXAMPLE = r'''-- EXAMPLE (an EASY held-tool game — study the shape, then write your OWN different easy game):
return {
    name = "Garden Splash",
    task = "so101_scoop_pour",
    skill = "scoop and pour with a held tool",
    setup = function(ctx)
        local c = ctx.region.center
        ctx.state.bucket = ctx.attachTool({ Size = Vector3.new(1.4, 1.2, 1.4),
            Color = Color3.fromRGB(150, 110, 70), Shape = Enum.PartType.Cylinder }, CFrame.new(0, -1.3, 0))
        ctx.state.pond = ctx.spawnBin(c + Vector3.new(-2.5, -0.4, 0), Color3.fromRGB(40, 130, 230), Vector3.new(3, 1, 3))
        ctx.state.plant = ctx.spawnBin(c + Vector3.new(2.5, -0.4, 0), Color3.fromRGB(70, 170, 70), Vector3.new(2, 1, 2))
        ctx.state.filled = false
        ctx.hud("SCOOP water from the blue pond → then POUR it on the green plant")
    end,
    step = function(ctx, dt)
        local b = ctx.state.bucket
        if not (b and b.Parent) then return 0, "idle" end
        if not ctx.state.filled and ctx.dist(b.Position, ctx.state.pond.Position) < 2.4 then
            ctx.state.filled = true; b.Color = Color3.fromRGB(40, 130, 230)
            ctx.burst(b.Position, Color3.fromRGB(60, 150, 255)); ctx.hud("Got water! Now POUR it on the green plant")
        end
        if ctx.state.filled and ctx.dist(b.Position, ctx.state.plant.Position) < 2.4 then
            ctx.popup(ctx.state.plant.Position, "BLOOM!", Color3.fromRGB(120, 255, 120)); ctx.win(10); return 10, "pour"
        end
        local goal = ctx.state.filled and ctx.state.plant or ctx.state.pond
        return -0.05 * ctx.dist(b.Position, goal.Position), ctx.state.filled and "pour" or "scoop"
    end,
}'''

DIRECTOR_SYSTEM = (
    "You design fun, EASY, juicy robot-arm mini-games on a small table where every play session "
    "secretly collects robot training data. Rules: generous tolerances (>= 2 studs), a round winnable "
    "in ~10-20s by a casual player, a crystal-clear goal, and juicy feedback (popups / bursts / "
    "sounds). NEVER require precise stacking, exact ordering, balancing, or tight insertion — those "
    "are too hard to control."
)

# Easy mechanics are PICKED IN CODE (the model only themes them) — the model's untamable bias toward
# precise stacking games means free-form invention isn't reliably easy.
MECHANICS = [
    "SCOOP & POUR: the arm STARTS holding a bucket (ctx.attachTool({...}, CFrame.new(0,-1.3,0))). "
    "Dip the bucket into a blue 'source' zone to fill it (recolor it + burst), then move it over a "
    "target zone to pour. Win on pour. No grabbing.",
    "SWEEP: the arm STARTS holding a flat paddle (ctx.attachTool). Spawn 3-4 loose balls; push them "
    "into one BIG glowing zone. Win when all are inside (dist < 2.5). No grabbing.",
    "STAMP: the arm STARTS holding a stamp (ctx.attachTool). Spawn 3 glowing marks on the table; "
    "bring the stamp within ~2 studs of each to stamp it (burst + mark it done). Win when all stamped.",
    "DUNK: the arm STARTS holding an item (ctx.attachTool). Dip it into a pot zone (dist < 2.2), then "
    "lift it back above a height line. Win on lift-after-dunk. No grabbing.",
    "PUSH: one block sits on the table; nudge/push it (NO grabbing, just bump the gripper into it) "
    "into a BIG glowing zone (dist < 2.5). Win when it's inside.",
    "DROP-IN-BUCKET: spawn ONE ball (ctx.spawnCube); pick it up and drop it into a BIG bucket "
    "(spawnBin, generous). Win on drop-in (dist < 2.5).",
]

CODER_SYSTEM = (
    "You are an expert Roblox/Luau engineer. Write the Game ModuleScript for the described robot "
    "mini-game, against this contract:\n\n" + CTX_API + "\n\n" + EXAMPLE + "\n\n"
    "Rules: return ONLY the Luau (one `return { ... }` table, no markdown). Build everything inside "
    "the reachable region. Keep it robust (nil-check parts; objects can be destroyed mid-round). "
    "Label subgoals accurately and shape the reward densely. Make it FUN and juicy. Do NOT touch the "
    "arm internals, the camera, RemoteEvents, or HttpService — only use the ctx API."
)

GAME_DESIGN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "description": "catchy game name"},
        "task": {"type": "string", "description": "short snake_case dataset id, prefix so101_"},
        "skill": {"type": "string", "description": "robot skill it teaches"},
        "pitch": {"type": "string", "description": "one-line fun hook"},
        "objects": {"type": "string", "description": "what's on the table (cubes/bins/zones, colors, counts)"},
        "rules": {"type": "string", "description": "core loop, win/lose, scoring, timer, difficulty"},
        "juice": {"type": "string", "description": "the satisfying feedback on success"},
    },
    "required": ["name", "task", "skill", "pitch", "objects", "rules", "juice"],
}


async def design_game(client: CerebrasClient, theme: str = "") -> dict:
    mech = random.choice(MECHANICS)
    user = ("Theme this EXACT mechanic into a fresh, juicy game — keep the mechanic and its generous "
            "tolerances, change only the look / story / name / colors:\n" + mech)
    if theme:
        user += f"\nLoose theme idea: {theme}."
    design, _ = await client.structured(DIRECTOR_SYSTEM, user, GAME_DESIGN_SCHEMA,
                                        name="game_design", max_tokens=700, temperature=0.6)
    design["_mechanic"] = mech
    return design


async def code_game(client: CerebrasClient, design: dict) -> str:
    brief = (f"GAME: {design['name']}\nDATASET task id: {design['task']}\nSkill: {design['skill']}\n"
             f"Pitch: {design['pitch']}\nObjects: {design['objects']}\nRules: {design['rules']}\n"
             f"Juice: {design['juice']}\n")
    if design.get("_mechanic"):
        brief += ("BASE MECHANIC — implement EXACTLY this (no stacking/ordering/precision): "
                  + design["_mechanic"] + "\n")
    brief += "\nWrite the Game ModuleScript."
    t = await client.chat([{"role": "system", "content": CODER_SYSTEM}, {"role": "user", "content": brief}],
                          max_tokens=4000, temperature=0.5)
    return _strip_fences(t.text or "")


async def _repair_source(client: CerebrasClient, source: str) -> tuple[str, bool]:
    """Repair until the module both COMPILES (luau-compile) and RUNS cleanly (headless validator:
    setup + 200 steps against a mock kit). Returns (source, valid)."""
    from .game_validator import validate_game
    from .syntax import check
    for _ in range(3):
        err = check(source)
        if not err:
            ok, rerr = validate_game(source)
            if ok:
                return source, True
            err = ("Runtime error when the game actually runs: " + rerr +
                   "  (nil-check every field; never do arithmetic on a possibly-nil value)")
        t = await client.chat(
            [{"role": "system", "content": CODER_SYSTEM},
             {"role": "user", "content": f"This Game module has a problem:\n{err}\n\nFix it. Output "
              f"ONLY the corrected module:\n{source}"}],
            max_tokens=4000, temperature=0.3)
        source = _strip_fences(t.text or "")
    ok, _ = validate_game(source)
    return source, (check(source) is None and ok)


async def generate_in_family(client: CerebrasClient, family: str, on_event=None) -> dict:
    """Generate a game inside a structured task FAMILY: steered to the family's skill, varied across
    the family's axes, and deduped against everything generated in that family so far."""
    from .families import FAMILIES, family_context, is_duplicate, load_registry, save_design
    from .syntax import check
    if family not in FAMILIES:
        return await generate_robot_game(client, family, on_event)  # fall back: treat as a theme
    prior = load_registry().get(family, [])
    design = None
    for _ in range(3):  # resample until distinct from prior in this family
        sys = DIRECTOR_SYSTEM + family_context(family, prior)
        d, _t = await client.structured(sys, f"Design a fresh '{family}' game.",
                                        GAME_DESIGN_SCHEMA, name="game_design", max_tokens=700, temperature=1.0)
        d["family"] = family
        if not is_duplicate(d, prior):
            design = d
            break
        design = d
    save_design(family, design)
    if on_event:
        on_event({"type": "game_design", **design})
    source = await code_game(client, design)
    source, valid = await _repair_source(client, source)
    return {"design": design, "source": source, "compiles": valid}


EXTEND_SYSTEM = (
    DIRECTOR_SYSTEM + " IMPORTANT: the player has just MASTERED the previous game, so design the "
    "NEXT step of a progression — the SAME robot-skill family but escalated and fresh: more objects, "
    "tighter tolerances, time pressure, an added constraint, or a clever new twist. It must feel like "
    "a harder level, and collect richer / more varied demonstrations of that skill."
)


async def extend_robot_game(client: CerebrasClient, prev: dict, stats: dict, on_event=None) -> dict:
    """Gemma forges the NEXT, harder challenge after a game is mastered. Returns {design, source, compiles}."""
    from .syntax import check
    note = (f"Previous game (now mastered): '{prev.get('name')}' — skill: {prev.get('skill')}. "
            f"Player stats: {stats}. Design the next, harder challenge in this progression.")
    design, _ = await client.structured(EXTEND_SYSTEM, note, GAME_DESIGN_SCHEMA,
                                        name="game_design", max_tokens=700, temperature=0.95)
    if on_event:
        on_event({"type": "game_design", **design})
    source = await code_game(client, design)
    source, valid = await _repair_source(client, source)
    return {"design": design, "source": source, "compiles": valid}


async def generate_robot_game(client: CerebrasClient, theme: str = "", on_event=None) -> dict:
    """Design + build one robot-manipulation game (with a syntax-repair loop). Returns
    {design, source, compiles}."""
    from .syntax import check
    design = await design_game(client, theme)
    if on_event:
        on_event({"type": "game_design", **design})
    source = await code_game(client, design)
    source, valid = await _repair_source(client, source)
    return {"design": design, "source": source, "compiles": valid}
