"""Vision playtester: a QA agent that SEES the generated level and grades it.

Renders the build to an image (top-down + side views), sends it to Gemma-4 vision
for a playability critique + score, and applies safe geometric fixes (bridge
unreachable obby gaps, ensure a spawn exists). This is the swarm's multimodal agent.
"""
from __future__ import annotations

import math

from .cerebras import CerebrasClient
from .genre_common import emit_ev, op
from .render import render_data_uri

PLAYTEST_SYSTEM = """You are a strict QA PLAYTESTER for auto-generated Roblox games.
You are shown two orthographic renders of ONE level: LEFT = top-down map (X right, Z up),
RIGHT = side elevation (Z right, height up). Judge whether it looks like a PLAYABLE,
well-formed game. Consider: a clear path / sensible layout; platforms reachable (no absurd
gaps or huge vertical jumps); floating or overlapping parts; too empty or too cluttered;
presence of a spawn (green dot) and goal (gold dot).
Output ONLY JSON:
{"score": <integer 0-10>, "issues": ["short issue", ... up to 5], "verdict": "<one blunt sentence>"}"""


def _dist_xz(a, b) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2])


def _bridge_gaps(build: dict, threshold: float = 18.0, max_fix: int = 10) -> int:
    """Insert stepping-stone platforms across too-large obby gaps."""
    plats = [p for p in build["parts"] if p.get("folder") == "Platforms"]
    if len(plats) < 2:
        return 0
    plats.sort(key=lambda p: p["pos"][2])
    added = 0
    for a, b in zip(plats, plats[1:]):
        if added >= max_fix:
            break
        gap = _dist_xz(a["pos"], b["pos"])
        if gap <= threshold:
            continue
        n = min(int(gap // 14), max_fix - added)
        for i in range(1, n + 1):
            t = i / (n + 1)
            pos = [a["pos"][k] + (b["pos"][k] - a["pos"][k]) * t for k in range(3)]
            build["parts"].append(
                op("Platforms", f"Bridge_{added}", pos, (7, 1, 7), "#43d6ff", "Neon"))
            added += 1
    return added


def _ensure_spawn(build: dict) -> int:
    if any(p.get("name") == "Spawn" for p in build["parts"]):
        return 0
    parts = build["parts"]
    if not parts:
        return 0
    low = min(parts, key=lambda p: p["pos"][1])
    pos = [low["pos"][0], low["pos"][1] + 4, low["pos"][2]]
    build["parts"].append(
        op("_root", "Spawn", pos, (8, 1, 8), "#cfd8dc", "SmoothPlastic", klass="SpawnLocation"))
    return 1


async def run_playtest(client: CerebrasClient, build: dict, genre: str, name: str, on_event=None):
    emit_ev(on_event, "agent", id="playtester", role="QA", name="Playtester", status="working")
    data_uri = render_data_uri(build)
    try:
        critique, turn = await client.vision_json(
            PLAYTEST_SYSTEM,
            f"This is an auto-generated Roblox {genre} game called '{name}'. "
            "Grade its playability from these renders. Output only the JSON.",
            data_uri, max_tokens=1500)
    except Exception as e:
        emit_ev(on_event, "agent", id="playtester", status="done", detail=f"vision error: {str(e)[:60]}")
        return build, {"score": None, "issues": [], "verdict": "", "fixes": 0}

    try:
        score = int(critique.get("score", 7))
    except (TypeError, ValueError):
        score = 7
    issues = [str(x) for x in (critique.get("issues") or [])][:5]
    verdict = str(critique.get("verdict", ""))

    before = len(build["parts"])
    fixes = _ensure_spawn(build)
    if genre == "obby":
        fixes += _bridge_gaps(build)
    new_ops = build["parts"][before:]
    if new_ops:  # stream the fix parts so the live plugin build adds them too
        emit_ev(on_event, "stage", ops=new_ops)

    # re-render so the UI shows the fixed level
    final_uri = render_data_uri(build) if fixes else data_uri
    emit_ev(on_event, "playtest", image=final_uri, before_image=data_uri,
            score=score, issues=issues, verdict=verdict, fixes=fixes,
            tps=round(turn.tokens_per_sec))
    emit_ev(on_event, "agent", id="playtester", status="done",
            detail=f"score {score}/10 · {fixes} fixes · {round(turn.tokens_per_sec)} tok/s")
    return build, {"score": score, "issues": issues, "verdict": verdict, "fixes": fixes}
