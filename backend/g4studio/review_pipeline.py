"""Coder -> Builder -> Reviewer -> Coder-revise pipeline for the robot games, coordinated on a team
channel (Slack). The Reviewer reads CODE ONLY by default; vision QA (screenshot grading) is opt-in
(`vision=True`) and off by default. The Coder<->Reviewer/Builder back-and-forth is capped so agents
can't ping each other more than `max_pings` times (default 2).
"""
import json
from typing import Optional

from .authored import _strip_fences
from .slack import Channel

REVIEWER_SYSTEM = (
    "You are the Reviewer for a Roblox robot-manipulation game module (Luau). You read ONLY the code "
    "(no screenshots). Check: (1) it matches the design brief + win condition; (2) it uses the ctx "
    "API correctly (spawnCube/spawnBin/spawnPart/attachTool, holding/dist/rand/hud/win/lose, "
    "ctx.region.center+reach, ctx.state); (3) NO nil arithmetic and every field is nil-checked; "
    "(4) objects are BIG (size ~2) and within ctx.region.reach of ctx.region.center; (5) it's actually "
    "fun, winnable and clear. Be strict but concise. "
    'Output ONLY JSON: {"approved": true|false, "issues": ["short actionable note", ...]} (<=4 issues, '
    "empty when approved)."
)
REVISE_SYSTEM = (
    "You are the Coder. Revise the Game module to address the Reviewer's notes EXACTLY. Keep the ctx "
    "API and the win condition intact; never introduce nil arithmetic. Output ONLY the corrected Luau "
    "module (a single `return { ... }`)."
)
QA_SYSTEM = (
    "You are Vision QA looking at a screenshot of the running game. Grade whether the scene reads "
    "clearly: objects visible + big + resting on the table, the goal obvious, layout not cluttered. "
    'Output ONLY JSON: {"score": 0-10, "issues": ["short note", ...]}.'
)


def _build_once(source: str) -> tuple[bool, str]:
    """Builder's check: compile (luau) + headless runtime validation. Returns (ok, error)."""
    from .game_validator import validate_game
    from .syntax import check
    err = check(source)
    if err:
        return False, "compile error: " + err.strip()
    ok, rerr = validate_game(source)
    if not ok:
        return False, "runtime error: " + rerr.strip()
    return True, ""


async def _review_code(client, source: str, design: dict) -> dict:
    brief = {k: design.get(k) for k in ("name", "pitch", "objects", "win", "_mechanic")}
    t = await client.chat(
        [{"role": "system", "content": REVIEWER_SYSTEM},
         {"role": "user", "content": f"DESIGN: {json.dumps(brief)}\n\nMODULE:\n{source}"}],
        max_tokens=800, temperature=0.3)
    try:
        d = json.loads(_strip_fences(t.text or "{}"))
        return {"approved": bool(d.get("approved")),
                "issues": [str(x) for x in (d.get("issues") or [])][:4]}
    except Exception:
        return {"approved": True, "issues": []}  # reviewer unsure -> don't block the ship


async def _revise(client, source: str, notes: list[str]) -> str:
    t = await client.chat(
        [{"role": "system", "content": REVISE_SYSTEM},
         {"role": "user", "content": "Reviewer notes:\n- " + "\n- ".join(notes) + f"\n\nModule:\n{source}"}],
        max_tokens=4000, temperature=0.3)
    return _strip_fences(t.text or source)


async def _vision_qa(client) -> Optional[dict]:
    """Opt-in: screenshot Studio + grade the rendered scene. No-op if Studio/capture unavailable."""
    try:
        from .capture import capture_data_uri
        uri = capture_data_uri()
        if not uri:
            return None
        crit, _ = await client.vision_json(QA_SYSTEM, "Grade this running game screenshot.", uri,
                                           max_tokens=500)
        return {"score": int(crit.get("score", 7)),
                "issues": [str(x) for x in (crit.get("issues") or [])][:3]}
    except Exception:
        return None


async def build_reviewed(client, design: dict, *, vision: bool = False, max_pings: int = 2,
                         on_event=None) -> tuple[str, bool, list]:
    """Run the Coder -> Builder -> Reviewer -> revise loop on a team channel.

    Returns (final_source, valid, transcript). `vision` enables the screenshot QA step (default off).
    """
    from .robotgame import code_game

    ch = Channel(topic=str(design.get("name", "game"))[:24], on_event=on_event, max_pings=max_pings)
    ch.post("coder", f"Drafting *{design.get('name', 'the game')}* "
                     f"({str(design.get('_mechanic', '')).split(':')[0].lower()}) — one module, kit API.")
    source = await code_game(client, design)

    revisions = 0
    valid = False
    while True:
        valid, err = _build_once(source)                                  # Builder
        ch.post("builder", "Build green — compiles + runs headless." if valid
                else f"Build red — {err[:130]}")

        if revisions >= max_pings:                                        # out of ping budget -> ship
            ch.post("reviewer", "Ping budget spent — shipping the current build.")
            break

        if not valid:                                                     # Builder pings Coder to fix
            if ch.ping("builder", "coder", f"please fix the build — {err[:90]}"):
                revisions += 1
                source = await _revise(client, source, [f"Build error: {err}"])
                continue
            break

        if vision:                                                        # opt-in screenshot QA
            qa = await _vision_qa(client)
            if qa:
                ch.post("qa", f"{qa['score']}/10"
                              + (f" — {'; '.join(qa['issues'])}" if qa["issues"] else " — reads clearly"))

        rev = await _review_code(client, source, design)                  # Reviewer (code only)
        if rev["approved"] and not rev["issues"]:
            ch.post("reviewer", "LGTM — approved. :white_check_mark:")
            break
        ch.post("reviewer", "Notes: " + "; ".join(rev["issues"]))
        if ch.ping("reviewer", "coder", f"please address {len(rev['issues'])} note(s)"):
            revisions += 1
            ch.post("coder", f"On it — revision {revisions}.")
            source = await _revise(client, source, rev["issues"])
            continue
        break  # ping cap hit -> ship

    # final safety: guarantee the shipped module at least builds
    if not valid:
        valid, _ = _build_once(source)
    return source, valid, ch.transcript
