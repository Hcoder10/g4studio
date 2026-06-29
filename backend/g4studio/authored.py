"""The harness: Gemma-4-31b AUTHORS the whole game — full control, no presets — but as
THREE correctly-separated parts so it runs the Roblox way:

  BUILD   -> constructs the STATIC world (geometry + lighting). Run ONCE by the plugin
             in Studio EDIT mode (editor/build work). No gameplay here.
  SERVER  -> a Server Script (ServerScriptService) — runs at game runtime: scoring,
             win/lose, Touched handlers, server loops, leaderstats.
  CLIENT  -> a LocalScript (StarterPlayerScripts) — runs on each client at runtime:
             UI/HUD, local effects, camera, input.

This fixes the bug where gameplay ran in the plugin/edit runtime and never tied to a real
play session. The harness still only catches what the model is bad at (QA + enum validation
+ the real-Studio vision loop) — it never substitutes a preset.
"""
from __future__ import annotations

import re
import time

from .cerebras import CerebrasClient
from .genre_common import emit_ev
from .validate import MATERIALS, PART_TYPES, find_api_issues

CODER_SYSTEM = r"""You are a master Roblox engineer with FULL creative control. Author a complete
game as THREE clearly separated parts so it runs correctly in Roblox. Output EXACTLY this format,
using the marker lines verbatim:

-- TITLE: <short catchy game name>
-- ===== BUILD =====
<Luau that builds the STATIC WORLD ONLY (runs ONCE in Studio edit mode). Build it procedurally,
 with helper functions + loops/math so it's coherent and lively:
 - FIRST, clear any previous build so re-running is clean:
     local old = workspace:FindFirstChild("G4Game"); if old then old:Destroy() end
 - Make helpers for repeated props from PRIMITIVES, e.g. makeTree(x,z), makeRock(x,z), using Parts
   with .Shape (Enum.PartType.Ball/Cylinder/Block) or WedgePart, .Material, .Color=Color3.fromRGB,
   .Anchored=true, and PointLight for glows. Group props in a Model.
 - Lay out the world with LOOPS/MATH for real structure: a bounded floor + perimeter walls; rows,
   rings (math.sin/cos), grids, or clusters; a clear SpawnLocation; the objective placed purposefully.
   Vary scale/rotation a little so nothing is copy-pasted.
 - Parent everything under a Folder "G4Game" in Workspace, grouped in subfolders.
 - Set lighting/atmosphere to fit the theme (game.Lighting: ClockTime, Ambient, FogColor/FogEnd, an Atmosphere).
 DO NOT put gameplay, event handlers, leaderstats, or player logic here — those go in SERVER/CLIENT below.>
-- ===== SERVER =====
<Luau for a SERVER Script that runs at game RUNTIME (in ServerScriptService). ALL server gameplay:
 leaderstats, scoring, win/lose, part.Touched handlers, NPC/enemy logic, server loops via
 task.spawn(function() while true do ... task.wait(t) end end). It references the already-built
 world via workspace:WaitForChild("G4Game"). Handle Players.PlayerAdded AND Players:GetPlayers().
 To talk to clients, create RemoteEvents in ReplicatedStorage.>
-- ===== CLIENT =====
<Luau for a LocalScript that runs at game RUNTIME on each client (in StarterPlayerScripts). UI/HUD,
 score display, local effects, camera, input. Use local player = game.Players.LocalPlayer and
 player:WaitForChild("PlayerGui"). Read leaderstats / listen to the server's RemoteEvents.>

Rules: only REAL Roblox API and Enums; never index a possibly-nil value (FindFirstChild /
WaitForChild, use HumanoidRootPart not PrimaryPart); never loop without a task.wait. Make a real,
lively, atmospheric game with a clear objective. Output ONLY the three sections."""

QA_SYSTEM = r"""You are a senior Roblox engineer reviewing a 3-part game script (BUILD / SERVER /
CLIENT). Fix every bug WITHOUT changing the game's design: invalid Enums/API, nil indexing,
loops missing task.wait, undefined vars, wrong service, things that error at runtime, and anything
in the wrong part (gameplay in BUILD, build in SERVER). Also ensure BUILD has no player/gameplay
logic. KEEP the exact `-- TITLE:` line and the `-- ===== BUILD/SERVER/CLIENT =====` markers and the
three-part structure. Output ONLY the corrected three-part script."""

API_REPAIR_SYSTEM = r"""You are fixing a Roblox script. Replace ONLY the invalid Roblox API usages
listed below with correct, real members that fit the intent (e.g. a rock should use Slate or Basalt).
Change NOTHING else. KEEP the `-- TITLE:` line and the `-- ===== BUILD/SERVER/CLIENT =====` markers.
Output ONLY the full corrected script."""

REVISE_SYSTEM = r"""You are improving the WORLD of a Roblox game you built. A playtester looked at a
screenshot of the level in Studio and gave feedback. Rewrite ONLY the BUILD code to improve the
world (layout, density, spread, a clearly bounded arena, decoration, structure) — keep the same
theme and objective. Output ONLY the corrected BUILD Luau (no markers, just the build code)."""

_SECTION_RE = re.compile(r"--\s*=+\s*(BUILD|SERVER|CLIENT)\s*=+", re.I)


def _strip_fences(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _force_fix(src: str) -> str:
    if not src:
        return src
    src = re.sub(r"Enum\.Material\.(\w+)",
                 lambda m: m.group(0) if m.group(1) in MATERIALS else "Enum.Material.SmoothPlastic", src)
    src = re.sub(r"Enum\.PartType\.(\w+)",
                 lambda m: m.group(0) if m.group(1) in PART_TYPES else "Enum.PartType.Block", src)
    return src


def _split_sections(text: str):
    text = _strip_fences(text)
    title = "G4 Game"
    m = re.search(r"--\s*TITLE:\s*(.+)", text)
    if m:
        title = m.group(1).strip()[:48]
    parts = _SECTION_RE.split(text)
    sections = {"BUILD": "", "SERVER": "", "CLIENT": ""}
    i = 1
    while i + 1 < len(parts):
        key = parts[i].upper()
        if key in sections:
            sections[key] = parts[i + 1].strip()
        i += 2
    return title, sections["BUILD"], sections["SERVER"], sections["CLIENT"]


async def run_authored(prompt: str, client: CerebrasClient, on_event=None,
                       feedback=None) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    turns = []
    user = prompt if not feedback else prompt + "\n\nIMPROVE ON YOUR LAST ATTEMPT: " + feedback

    emit_ev(on_event, "agent", id="coder", role="Coder", name="Coder", status="working")
    ct = await client.chat([{"role": "system", "content": CODER_SYSTEM},
                            {"role": "user", "content": user}], max_tokens=16000, temperature=0.65)
    turns.append(ct)
    raw = ct.text or ""
    emit_ev(on_event, "agent", id="coder", status="done",
            detail=f"{raw.count(chr(10)) + 1} lines · {round(ct.tokens_per_sec)} tok/s")

    emit_ev(on_event, "agent", id="qa", role="QA", name="Reviewer", status="working")
    qt = await client.chat([{"role": "system", "content": QA_SYSTEM},
                            {"role": "user", "content": raw}], max_tokens=16000, temperature=0.2)
    turns.append(qt)
    fixed = qt.text or ""
    if len(fixed) < 200:
        fixed = raw
    emit_ev(on_event, "agent", id="qa", status="done", detail=f"reviewed · {round(qt.tokens_per_sec)} tok/s")

    # API validation on the combined text, then the model repairs (stays in control)
    issues = find_api_issues(fixed)
    if issues:
        emit_ev(on_event, "agent", id="validator", role="Validator", name="API Validator", status="working")
        rt = await client.chat([{"role": "system", "content": API_REPAIR_SYSTEM},
                                {"role": "user", "content": "INVALID API:\n" + "\n".join(issues) +
                                 "\n\nSCRIPT:\n" + fixed}], max_tokens=16000, temperature=0.1)
        turns.append(rt)
        rfixed = rt.text or ""
        if len(rfixed) > 200:
            fixed = rfixed
        emit_ev(on_event, "agent", id="validator", status="done", detail=f"fixed {len(issues)} API error(s)")

    title, build_src, server_src, client_src = _split_sections(fixed)
    if not build_src and not server_src:  # markers missing -> treat whole as a runtime server script
        server_src = _strip_fences(fixed)
    build_src, server_src, client_src = _force_fix(build_src), _force_fix(server_src), _force_fix(client_src)

    build = {"authored": True, "name": title, "build": build_src,
             "server": server_src, "client": client_src}
    wall_ms = (time.perf_counter() - t0) * 1000.0
    metrics = {
        "genre": "authored", "name": title, "agents": len(turns), "wall_ms": round(wall_ms),
        "lines": (build_src + server_src + client_src).count("\n") + 1,
        "completion_tokens": sum(t.completion_tokens for t in turns),
        "agent_tps": [round(t.tokens_per_sec) for t in turns],
        "api_fixes": len(issues),
        "has_server": bool(server_src), "has_client": bool(client_src),
    }
    emit_ev(on_event, "authored_done", name=title, lines=metrics["lines"], wall_ms=metrics["wall_ms"])
    return build, metrics
