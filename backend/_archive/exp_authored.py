"""RESEARCH HARNESS v2 — model-authored games, FULL control, no presets.

Pipeline: Coder writes a complete world+game Luau -> QA agent audits & fixes bugs
(without changing the design). Tests across varied prompts; saves scripts to out/.

Run: python backend/exp_authored.py
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from g4studio.cerebras import CerebrasClient  # noqa: E402
from g4studio.validate import find_api_issues, MATERIALS, PART_TYPES  # noqa: E402

API_REPAIR_SYSTEM = """You are fixing a Luau script. Replace ONLY the invalid Roblox API usages
listed below with correct, real members that fit the intent (e.g. a rock should use Slate or Basalt).
Change NOTHING else about the script. Output ONLY the full corrected Luau."""

CODER_SYSTEM = r"""You are a master Roblox Luau engineer with FULL creative control. Write ONE complete
server Script that, when it runs once on the server, BUILDS the entire game world AND implements all
gameplay. You decide everything — there are no templates.

Start with a comment:  -- TITLE: <a short catchy game name>

WORLD (build it procedurally, with helper functions + loops/math so it's coherent and lively):
- Make helpers for repeated props from PRIMITIVES, e.g. makeTree(x,z), makeRock(x,z), using Parts
  with .Shape (Enum.PartType.Ball/Cylinder/Block) or WedgePart, .Material, .Color=Color3.fromRGB,
  .Anchored=true, and PointLight for glows. Group props in a Model.
- Lay out the world with LOOPS/MATH for real structure: a bounded floor + perimeter walls; rows,
  rings (math.sin/cos), grids, or clusters; a clear SpawnLocation; the objective placed purposefully.
  Vary scale/rotation a little so nothing is copy-pasted.
- Parent everything under a Folder "G4Game" in Workspace, grouped in subfolders.
- Set lighting/atmosphere to fit the theme (game.Lighting: ClockTime, Ambient, FogColor/FogEnd, an Atmosphere).

GAMEPLAY: leaderstats; Touched / ClickDetector handlers; timers via task.spawn(function() while ...
task.wait(t) end end); clear win/lose. Handle Players.PlayerAdded AND Players:GetPlayers().

ROBUSTNESS (avoid runtime errors): only use REAL Roblox Enums/API; never index a possibly-nil value
(use FindFirstChild and the character's HumanoidRootPart, not PrimaryPart); never loop without a wait.
Make it a real, lively, atmospheric game with a clear objective. Output ONLY valid Luau."""

QA_SYSTEM = r"""You are a senior Roblox engineer doing strict code review on a Luau Script that builds
and runs a game. Find and FIX every bug WITHOUT changing the game's design or content:
- invalid Enum members (Font/Material/PartType/etc. that don't exist) -> use real ones
- indexing a possibly-nil value (e.g. character.PrimaryPart, FindFirstChild results) -> guard it
- loops with no task.wait (would freeze) -> add a wait
- undefined variables, wrong API names/signatures, bad parenting or ordering
- anything that would error at runtime
Keep ALL world-building and gameplay exactly. Output ONLY the corrected, complete Luau."""

PROMPTS = [
    "a spooky forest where you collect 8 glowing gems among the trees, torches light the area, collect all to win",
    "a lava-floor battle arena: grab a sword from the center and knock other players into the lava, last alive wins",
    "a clicker game: click a giant glowing cube in the middle of a neon city to earn points, buy bigger cubes",
    "a candy land obstacle course: jump across floating lollipops and gumdrops to reach the chocolate castle",
]


def strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _force_fix(src: str) -> str:
    """Deterministic safety net: swap any still-invalid enum for a safe default."""
    src = re.sub(r"Enum\.Material\.(\w+)",
                 lambda m: m.group(0) if m.group(1) in MATERIALS else "Enum.Material.SmoothPlastic", src)
    src = re.sub(r"Enum\.PartType\.(\w+)",
                 lambda m: m.group(0) if m.group(1) in PART_TYPES else "Enum.PartType.Block", src)
    return src


async def author(client, prompt):
    t = await client.chat([{"role": "system", "content": CODER_SYSTEM},
                           {"role": "user", "content": prompt}], max_tokens=14000, temperature=0.65)
    src = strip_fences(t.text or "")
    q = await client.chat([{"role": "system", "content": QA_SYSTEM},
                           {"role": "user", "content": src}], max_tokens=14000, temperature=0.2)
    fixed = strip_fences(q.text or "")
    if len(fixed) < 200:  # QA failed, keep original
        fixed = src

    issues = find_api_issues(fixed)
    if issues:  # let the MODEL fix its own hallucinated API (stays in control)
        r = await client.chat([{"role": "system", "content": API_REPAIR_SYSTEM},
                               {"role": "user", "content": "INVALID API:\n" + "\n".join(issues) +
                                "\n\nSCRIPT:\n" + fixed}], max_tokens=14000, temperature=0.1)
        rfixed = strip_fences(r.text or "")
        if len(rfixed) > 200:
            fixed = rfixed
    remaining = find_api_issues(fixed)
    fixed = _force_fix(fixed)  # guarantee no invalid-enum crash ships

    title = "Untitled"
    m = re.search(r"--\s*TITLE:\s*(.+)", fixed)
    if m:
        title = m.group(1).strip()
    return fixed, title, issues, remaining, t, q


async def main():
    client = CerebrasClient()
    out_dir = os.path.join(os.path.dirname(__file__), "..", "out")
    os.makedirs(out_dir, exist_ok=True)
    for i, prompt in enumerate(PROMPTS):
        fixed, title, issues, remaining, t, q = await author(client, prompt)
        path = os.path.join(out_dir, f"authored_{i}.lua")
        open(path, "w", encoding="utf-8").write(fixed)
        # quick heuristic checks
        checks = {
            "Instance.new": fixed.count("Instance.new"),
            "helpers(func)": fixed.count("function"),
            "loops(for)": fixed.count("for "),
            "leaderstats": "leaderstats" in fixed,
            "task.spawn": fixed.count("task.spawn"),
            "PointLight": "PointLight" in fixed,
            "win-ish": any(w in fixed.lower() for w in ("win", "wins", "escaped", "victory")),
        }
        print(f"[{i}] '{title}'  ({fixed.count(chr(10))+1} lines, code {t.completion_tokens}t/"
              f"{round(t.tokens_per_sec)}tps, qa {q.completion_tokens}t)")
        print(f"     {checks}")
        if issues:
            print(f"     API issues found: {issues} | after model-repair: {remaining or 'NONE'}")
        print(f"     -> {os.path.basename(path)}")
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
