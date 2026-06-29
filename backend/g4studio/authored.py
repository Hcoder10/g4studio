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

CODER_SYSTEM = r"""You are a master Roblox Luau engineer with FULL creative control. Author a complete
game. You decide everything — there are no templates. Output it as THREE parts (so each runs in the
right place), using these marker lines verbatim:

-- TITLE: <a short catchy game name>
-- ===== BUILD =====
-- ===== SERVER =====
-- ===== CLIENT =====

BUILD (runs ONCE in Studio edit mode to construct the static world — no gameplay here). Build it
procedurally, with helper functions + loops/math so it's coherent and lively:
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

SERVER (a Script in ServerScriptService, runs at game runtime). Implement the COMPLETE game the
player asked for, COHESIVELY — you can see everything here, so make the parts actually work together.
If the game needs several systems (a lobby/intermission, waves/rounds, an economy/shop, enemies AND
the things that fight them, scoring), build them ALL in this one script so they share state directly:
- Build every MOVING/INTERACTIVE entity (enemies, mobs, projectiles, NPCs, pickups) from PRIMITIVES
  and SET model.PrimaryPart to a Part named "HumanoidRootPart" — NEVER from a loaded model asset
  (LoadAsset models have no PrimaryPart and break movement). Move them via PrimaryPart.CFrame each step.
- ONE source of truth for shared values: per-player via player:SetAttribute("Gold"/"Score"); global
  via workspace:SetAttribute("Wave"/"BaseHealth"/"State"). (The CLIENT reads these directly.)
- Reference the SAME path/positions the BUILD made (store the enemy path as a Folder of waypoint
  parts, or attributes the BUILD set) via workspace:WaitForChild("G4Game"); enemies and towers MUST
  use the same coordinates.
- A clear win AND lose condition that actually FIRES; reward the player's main action; loops use task.wait.
- GAME FEEL on every key moment: a Sound, a ParticleEmitter:Emit() burst, a tween.

CLIENT (a LocalScript in StarterPlayerScripts, runs on each client). The WHOLE player-facing layer:
- a clean HUD that READS the server's attributes (player:GetAttribute + player:GetAttributeChangedSignal,
  workspace:GetAttributeChangedSignal) — show gold/score/wave/health and the objective;
- input/placement (mouse, UserInputService) firing RemoteEvents to the server;
- local juice: hit/pickup sounds, particle bursts, TweenService UI animation, floating damage/gold
  popups (a BillboardGui adornee'd to the thing), and a real victory/defeat screen with payoff.
- Use local player = game.Players.LocalPlayer, player:WaitForChild("PlayerGui").

ROBUSTNESS: only REAL Roblox Enums/API; never index a possibly-nil value (FindFirstChild / nil-check;
the character's HumanoidRootPart, not PrimaryPart); never loop without task.wait; RemoteEvents live in
ReplicatedStorage — the SERVER creates them, the CLIENT WaitForChild's them.
Make it a COMPLETE, lively, FUN game with clear feedback. Output ONLY the three parts."""

QA_SYSTEM = r"""You are a senior Roblox engineer reviewing a 3-part Roblox game (BUILD / SERVER /
CLIENT) written to fulfill a player's request, which you are given. Two jobs:
1) Make sure it actually DELIVERS the requested game — the objective, the core mechanics, and the
   win/lose all match what was asked, and nothing important is missing or contradicts it. Use your
   judgment about what THIS game needs; the checklist below is guidance, not rigid rules that apply
   to every game.
2) Fix bugs that would break it at runtime:
   - invalid Enum members (Font/Material/PartType/etc. that don't exist) -> use real ones
   - indexing a possibly-nil value (e.g. character.PrimaryPart, FindFirstChild results) -> guard it
   - loops with no task.wait (would freeze) -> add a wait
   - undefined variables, wrong API names/signatures, bad parenting or ordering, anything that errors
Keep the design and content. KEEP the `-- TITLE:` line and the `-- ===== BUILD/SERVER/CLIENT =====`
markers. Output ONLY the corrected three-part script."""

API_REPAIR_SYSTEM = r"""You are fixing a Luau script. Replace ONLY the invalid Roblox API usages listed
below with correct, real members that fit the intent (e.g. a rock should use Slate or Basalt). Change
NOTHING else about the script. KEEP the `-- TITLE:` line and the `-- ===== BUILD/SERVER/CLIENT =====`
markers. Output ONLY the full corrected script."""

REVISE_SYSTEM = r"""You are improving a Roblox game you wrote. A playtester looked at a screenshot of
your level in Studio and gave feedback. Improve the WORLD-BUILDING (layout, density, spread, a clearly
bounded arena, decoration, structure) to address it — keep the same theme and objective. You are given
the BUILD code; output ONLY the corrected BUILD Luau."""

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
    qt = await client.chat(
        [{"role": "system", "content": QA_SYSTEM},
         {"role": "user", "content": f"The player requested:\n{prompt}\n\nReview this 3-part script:\n{raw}"}],
        max_tokens=16000, temperature=0.2)
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
