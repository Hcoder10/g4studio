"""Gemma generates FUN robot-manipulation games that collect training data as you play.

The arm, IK, hover-control and trace recording are the fixed kit; Gemma only writes the Game module
(scene + rules + scoring + juice + per-step skill labels). A Director invents the game, a Coder
builds it against the ctx API, and we syntax-check the result.
"""
import asyncio
import os

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
- ctx.spawnPart({...}) -> Part : a custom anchored part; NOT graspable unless ctx.makeGraspable(p).
- ctx.makeGraspable(part).
- ctx.hud(text) : the big top text — show the goal + score + countdown.
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

EXAMPLE = r'''-- EXAMPLE (study the shape, then write your OWN different game):
return {
    name = "Color Rush",
    task = "so101_color_sort",
    skill = "color sorting + place",
    setup = function(ctx)
        local c = ctx.region.center
        ctx.state.redBin = ctx.spawnBin(c + Vector3.new(-3, -0.5, 0), Color3.fromRGB(220, 60, 60))
        ctx.state.blueBin = ctx.spawnBin(c + Vector3.new(3, -0.5, 0), Color3.fromRGB(60, 110, 220))
        local red = ctx.rand(0, 1) > 0.5
        ctx.state.col = red and Color3.fromRGB(220, 60, 60) or Color3.fromRGB(60, 110, 220)
        ctx.state.bin = red and ctx.state.redBin or ctx.state.blueBin
        ctx.state.cube = ctx.spawnCube(c + Vector3.new(ctx.rand(-1.5, 1.5), 0.5, 1.5), ctx.state.col)
        ctx.hud("Drop the cube in the matching bin!  (R/F up-down, click grab)")
    end,
    step = function(ctx, dt)
        local cube, bin = ctx.state.cube, ctx.state.bin
        if not cube or not cube.Parent then return 0, "idle" end
        local held = ctx.holding() == cube
        local d = ctx.dist(cube.Position, bin.Position)
        if d < 1.6 and cube.Position.Y < bin.Position.Y + 1.2 and not held then
            ctx.burst(cube.Position, ctx.state.col); ctx.popup(cube.Position, "NICE!", ctx.state.col)
            ctx.win(10); return 10, "place"
        end
        if held then return -0.05 * d, (d < 2.5) and "place" or "transport"
        else return -0.03 * ctx.dist(ctx.arm.tip.Position, cube.Position), "reach" end
    end,
}'''

DIRECTOR_SYSTEM = (
    "You are a game director. Invent ONE fun, juicy, addictive round-based Roblox mini-game where "
    "the player teleoperates a realistic SO-101 robot ARM (reach, grab, move, place objects on a "
    "small table) — and the FUN is the manipulation challenge itself. Crucial twist: winning must "
    "REQUIRE good arm control, because every play session is secretly collecting robot training "
    "data. Keep it buildable from cubes / bins / zones in a small reachable workcell, and make it "
    "genuinely satisfying (timers, combos, escalating difficulty, juicy feedback). Be inventive and "
    "vary the SKILL collected (sorting, stacking, speed-picking, insertion, balancing, sequencing)."
)

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
    user = "Invent a robot-arm manipulation game." + (f" Theme/idea: {theme}" if theme else "")
    design, _ = await client.structured(DIRECTOR_SYSTEM, user, GAME_DESIGN_SCHEMA,
                                        name="game_design", max_tokens=700, temperature=0.9)
    return design


async def code_game(client: CerebrasClient, design: dict) -> str:
    brief = (f"GAME: {design['name']}\nDATASET task id: {design['task']}\nSkill: {design['skill']}\n"
             f"Pitch: {design['pitch']}\nObjects: {design['objects']}\nRules: {design['rules']}\n"
             f"Juice: {design['juice']}\n\nWrite the Game ModuleScript.")
    t = await client.chat([{"role": "system", "content": CODER_SYSTEM}, {"role": "user", "content": brief}],
                          max_tokens=4000, temperature=0.5)
    return _strip_fences(t.text or "")


async def generate_robot_game(client: CerebrasClient, theme: str = "", on_event=None) -> dict:
    """Design + build one robot-manipulation game (with a syntax-repair loop). Returns
    {design, source, compiles}."""
    from .syntax import check
    design = await design_game(client, theme)
    if on_event:
        on_event({"type": "game_design", **design})
    source = await code_game(client, design)
    for _ in range(2):  # repair until it compiles
        err = check(source)
        if not err:
            break
        t = await client.chat(
            [{"role": "system", "content": CODER_SYSTEM},
             {"role": "user", "content": f"This Game module has a Luau compile error:\n{err}\n\n"
              f"Fix it. Output ONLY the corrected module:\n{source}"}],
            max_tokens=4000, temperature=0.3)
        source = _strip_fences(t.text or "")
    return {"design": design, "source": source, "compiles": check(source) is None}
