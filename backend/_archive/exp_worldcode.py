"""EXPERIMENT: can Gemma-4-31b write the WORLD-BUILDING code itself (full control),
not just gameplay? It writes ONE Luau script that builds the world procedurally
(loops/patterns) AND implements the game. We read the result to judge the approach.

Run: python backend/exp_worldcode.py "<prompt>"
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from g4studio.cerebras import CerebrasClient  # noqa: E402

SYSTEM = r"""You are a master Roblox Luau engineer with FULL creative control. Write ONE complete
server Script that, when it runs once on the server, BUILDS the entire game world AND implements
all gameplay. You decide everything — there are no templates.

WORLD (build it procedurally, with helper functions + loops/math so it's coherent and lively):
- Make small helpers for repeated props from PRIMITIVES, e.g.:
    local function makeTree(x, z)
        local m = Instance.new("Model"); m.Name = "Tree"
        local trunk = Instance.new("Part"); trunk.Shape = Enum.PartType.Cylinder ...
        local leaves = Instance.new("Part"); leaves.Shape = Enum.PartType.Ball ...
        ... parent into m, m.Parent = world ...
    end
  (Parts: set .Shape Ball/Cylinder/Block or use WedgePart; .Material (Neon/Wood/Grass/Slate/Marble/
   Concrete/Glass); .Color = Color3.fromRGB(...); .Anchored=true; add PointLight for glows.)
- Lay out the world with LOOPS/MATH for real structure: a bounded floor + perimeter walls; rows,
  rings (use math.sin/cos), grids, or clusters of props; a clear SpawnLocation; the objective placed
  purposefully. Vary scale/rotation slightly so it isn't copy-pasted.
- Parent everything under a Folder "G4Game" in Workspace, grouped in subfolders.
- Set lighting/atmosphere to fit the theme (game.Lighting: ClockTime, Ambient, FogColor/FogEnd, Atmosphere).

GAMEPLAY (after building): leaderstats; Touched / ClickDetector handlers; timers via
task.spawn(function() while true do ... task.wait(t) end end); a clear win/lose. Handle
Players.PlayerAdded AND existing Players:GetPlayers(). Guard nils (FindFirstChild/pcall).

Make it a real, lively, atmospheric game with a clear objective. Output ONLY valid Luau."""


async def main():
    prompt = " ".join(sys.argv[1:]) or \
        "a spooky forest where you collect 8 glowing gems among the trees, torches light the area, collect all to win"
    print(f"Prompt: {prompt}\n")
    client = CerebrasClient()
    turn = await client.chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=14000, temperature=0.6)
    src = turn.text or ""
    out = os.path.join(os.path.dirname(__file__), "..", "out", "worldcode.lua")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # strip ``` fences if present
    s = src.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    open(out, "w", encoding="utf-8").write(s)
    print(f"{turn.completion_tokens} tokens, {round(turn.tokens_per_sec)} tok/s, {round(turn.latency_ms)} ms")
    print(f"wrote {out} ({len(s)} chars, {s.count(chr(10))+1} lines)")
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
