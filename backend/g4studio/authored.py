"""The harness: Gemma-4-31b AUTHORS the whole game (world + gameplay) as one Luau
script — full control, no presets. The harness makes it reliable:

  Coder      -> writes the complete world-building + gameplay script
  QA         -> fixes logic bugs without changing the design
  Validator  -> deterministic Roblox-API check (the model's weak spot: hallucinated
                enums) feeds PRECISE errors back; the MODEL repairs them
  Safety-net -> any still-invalid enum is swapped for a safe default (never ships a crash)

The model decides everything; the harness only catches what it's bad at and asks it
to fix — it never substitutes a preset for the model's authorship.
"""
from __future__ import annotations

import re
import time

from .cerebras import CerebrasClient
from .genre_common import emit_ev
from .validate import MATERIALS, PART_TYPES, find_api_issues

CODER_SYSTEM = r"""You are a master Roblox Luau engineer with FULL creative control. Write ONE complete
server Script that, when it runs once on the server, BUILDS the entire game world AND implements all
gameplay. You decide everything — there are no templates.

Start with a comment:  -- TITLE: <a short catchy game name>

WORLD (build it procedurally, with helper functions + loops/math so it's coherent and lively):
- FIRST, clear any previous build so re-running is clean:
  `local old = workspace:FindFirstChild("G4Game"); if old then old:Destroy() end`
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

API_REPAIR_SYSTEM = r"""You are fixing a Luau script. Replace ONLY the invalid Roblox API usages listed
below with correct, real members that fit the intent (e.g. a rock should use Slate or Basalt). Change
NOTHING else about the script. Output ONLY the full corrected Luau."""

REVISE_SYSTEM = r"""You are improving a Roblox game you wrote. A playtester looked at a top-down + side
render of your level and gave feedback. Improve the WORLD-BUILDING (layout, density, spread, a clearly
bounded arena, decoration, structure) to address it — keep the gameplay and design intent. Output ONLY
the full corrected Luau."""


def _strip_fences(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _force_fix(src: str) -> str:
    src = re.sub(r"Enum\.Material\.(\w+)",
                 lambda m: m.group(0) if m.group(1) in MATERIALS else "Enum.Material.SmoothPlastic", src)
    src = re.sub(r"Enum\.PartType\.(\w+)",
                 lambda m: m.group(0) if m.group(1) in PART_TYPES else "Enum.PartType.Block", src)
    return src


async def run_authored(prompt: str, client: CerebrasClient, on_event=None,
                       feedback=None) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    turns = []
    user = prompt if not feedback else prompt + "\n\nIMPROVE ON YOUR LAST ATTEMPT: " + feedback

    emit_ev(on_event, "agent", id="coder", role="Coder", name="Coder", status="working")
    ct = await client.chat([{"role": "system", "content": CODER_SYSTEM},
                            {"role": "user", "content": user}], max_tokens=14000, temperature=0.65)
    turns.append(ct)
    src = _strip_fences(ct.text)
    emit_ev(on_event, "agent", id="coder", status="done",
            detail=f"{src.count(chr(10)) + 1} lines · {round(ct.tokens_per_sec)} tok/s")

    emit_ev(on_event, "agent", id="qa", role="QA", name="Reviewer", status="working")
    qt = await client.chat([{"role": "system", "content": QA_SYSTEM},
                            {"role": "user", "content": src}], max_tokens=14000, temperature=0.2)
    turns.append(qt)
    fixed = _strip_fences(qt.text)
    if len(fixed) < 200:
        fixed = src
    emit_ev(on_event, "agent", id="qa", status="done", detail=f"reviewed · {round(qt.tokens_per_sec)} tok/s")

    issues = find_api_issues(fixed)
    if issues:
        emit_ev(on_event, "agent", id="validator", role="Validator", name="API Validator", status="working")
        rt = await client.chat([{"role": "system", "content": API_REPAIR_SYSTEM},
                                {"role": "user", "content": "INVALID API:\n" + "\n".join(issues) +
                                 "\n\nSCRIPT:\n" + fixed}], max_tokens=14000, temperature=0.1)
        turns.append(rt)
        rfixed = _strip_fences(rt.text)
        if len(rfixed) > 200:
            fixed = rfixed
        emit_ev(on_event, "agent", id="validator", status="done",
                detail=f"fixed {len(issues)} API error(s)")
    fixed = _force_fix(fixed)
    # NOTE: the vision-feedback loop now runs in REAL Roblox Studio (plugin builds the
    # world in edit mode; server screenshots Studio via /api/vision -> Gemma grades ->
    # the model revises). See server.api_vision + the plugin.

    title = "G4 Game"
    m = re.search(r"--\s*TITLE:\s*(.+)", fixed)
    if m:
        title = m.group(1).strip()[:48]

    build = {"authored": True, "name": title, "script": fixed, "root": "G4Game"}
    wall_ms = (time.perf_counter() - t0) * 1000.0
    metrics = {
        "genre": "authored", "name": title, "agents": len(turns),
        "wall_ms": round(wall_ms), "lines": fixed.count("\n") + 1,
        "completion_tokens": sum(t.completion_tokens for t in turns),
        "agent_tps": [round(t.tokens_per_sec) for t in turns],
        "api_fixes": len(issues),
    }
    emit_ev(on_event, "authored_done", name=title, lines=metrics["lines"],
            wall_ms=metrics["wall_ms"], api_fixes=len(issues))
    return build, metrics
