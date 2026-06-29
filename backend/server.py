"""FastAPI server: serves the UI and streams the swarm over a WebSocket.

Run:  python backend/server.py   (then open http://127.0.0.1:8000)
"""
import asyncio
import os
import sys
import uuid

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(__file__))

from g4studio.swarm import generate_game  # noqa: E402
from g4studio.emit import build_to_rbxmx, build_to_luau  # noqa: E402
from g4studio.emit.plugin_ops import to_plugin_event  # noqa: E402
from g4studio.cerebras import CerebrasClient  # noqa: E402
from g4studio.capture import capture_data_uri  # noqa: E402
from g4studio.playtester import PLAYTEST_OPEN  # noqa: E402
from g4studio.authored import REVISE_SYSTEM, _strip_fences, _force_fix  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, "frontend")

app = FastAPI(title="G4 Studio")


@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))


@app.get("/health")
async def health():
    return {"ok": True}


# ---- AI playtester that actually PLAYS the game in a real Play session ----
LAST_GAME = {"prompt": "", "name": ""}
PLAYBOT = {"notes": []}

PLAYBOT_SYSTEM = (
    "You are an AI PLAYTESTER actively PLAYING a Roblox game to TEST it. You see a screenshot from "
    "the player's view plus the player's state. Verify the game WORKS and is PLAYABLE, make progress "
    "toward the objective, and report problems (can't move, fell off the map, nothing happens, looks "
    "broken, no clear objective, score never changes). Each step choose ONE action: 'forward','back',"
    "'left','right' (move relative to the camera), 'jump' (to climb/cross gaps), or 'wait' (observe). "
    'Output ONLY JSON: {"action":"<one>","note":"<short observation / any problem>",'
    '"done":<true when you have tested enough or are stuck/finished>,'
    '"verdict":"<when done: one blunt sentence>","score":<when done: 0-10 how playable>}'
)


@app.post("/api/playbot")
async def api_playbot(req: Request):
    body = await req.json()
    state = body.get("state") or {}
    step = int(body.get("step", 0))
    if step == 0:
        PLAYBOT["notes"] = []
    data_uri = capture_data_uri()
    msg = (f"Game: {LAST_GAME.get('name')}. Objective: {LAST_GAME.get('prompt')}. Step {step}/40. "
           f"Player state: pos={state.get('pos')}, score={state.get('leaderstats')}, "
           f"health={state.get('health')}. Decide your next action to play & test. Output only JSON.")
    if not data_uri:
        return {"action": "forward", "note": "no screenshot (is Studio in Play + visible?)",
                "done": step >= 6, "verdict": "could not see the game", "score": 3}
    client = CerebrasClient()
    try:
        crit, _ = await client.vision_json(PLAYBOT_SYSTEM, msg, data_uri, max_tokens=400, temperature=0.4)
        action = str(crit.get("action", "forward")).lower()
        note = str(crit.get("note", ""))
        if note:
            PLAYBOT["notes"].append(note)
        done = bool(crit.get("done")) or step >= 40
        out = {"action": action, "note": note, "done": done}
        if done:
            out["verdict"] = str(crit.get("verdict", "playtest complete"))
            try:
                out["score"] = int(crit.get("score", 6))
            except (TypeError, ValueError):
                out["score"] = 6
        return out
    finally:
        await client.aclose()


@app.post("/api/vision")
async def api_vision(req: Request):
    """Screenshot the REAL Roblox Studio window, have Gemma-4 grade the engine render,
    and (if weak) return a revised script for the plugin to rebuild. No sandbox."""
    body = await req.json()
    build_src = body.get("build") or body.get("script") or ""
    attempt = int(body.get("attempt", 0))
    data_uri = capture_data_uri()
    if not data_uri:
        return {"error": "Roblox Studio window not found or not visible"}
    client = CerebrasClient()
    try:
        crit, _vt = await client.vision_json(
            PLAYTEST_OPEN,
            "This is a screenshot of an auto-generated Roblox game level built in Studio. Grade it. Output only JSON.",
            data_uri, max_tokens=1200)
        try:
            score = int(crit.get("score", 7))
        except (TypeError, ValueError):
            score = 7
        issues = [str(x) for x in (crit.get("issues") or [])][:4]
        verdict = str(crit.get("verdict", ""))
        out = {"score": score, "issues": issues, "verdict": verdict}
        if score < 6 and attempt < 2 and len(build_src) > 50:
            rv = await client.chat(
                [{"role": "system", "content": REVISE_SYSTEM},
                 {"role": "user", "content":
                  f"A playtester looked at the level in Studio and scored it {score}/10. "
                  f"Issues: {'; '.join(issues)}. Verdict: {verdict}. Improve the world. BUILD code:\n{build_src}"}],
                max_tokens=14000, temperature=0.5)
            revised = _strip_fences(rv.text or "")
            if len(revised) > 100:
                out["revised_build"] = _force_fix(revised)
        return out
    finally:
        await client.aclose()


@app.post("/api/generate")
async def api_generate(req: Request):
    """One-shot generate for the Roblox Studio plugin: prompt -> build-ops + metrics.
    Also returns .rbxmx for the no-plugin fallback."""
    body = await req.json()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return {"error": "empty prompt"}
    build, metrics = await generate_game(prompt)
    return {
        "name": build.get("name"),
        "metrics": metrics,
        "build": build,
        "rbxmx": build_to_rbxmx(build),
    }


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


# ---- Streaming jobs for the plugin (poll-based; HttpService can't do WS) ----
JOBS: dict = {}


@app.post("/api/generate/start")
async def gen_start(req: Request):
    body = await req.json()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return {"error": "empty prompt"}
    job_id = uuid.uuid4().hex[:12]
    job = {"events": [], "done": False}
    JOBS[job_id] = job

    def on_event(e: dict) -> None:
        pe = to_plugin_event(e)
        if pe:
            job["events"].append(pe)

    async def run() -> None:
        try:
            build, metrics = await generate_game(prompt, on_event=on_event)
            done_ev = {"type": "done", "name": build.get("name"), "metrics": metrics}
            if build.get("segmented"):
                LAST_GAME["prompt"] = prompt
                LAST_GAME["name"] = build.get("name", "game")
                done_ev["segmented"] = True
                done_ev["shared"] = build.get("shared", [])
                done_ev["systems"] = build.get("systems", [])
                done_ev["server_bootstrap"] = build.get("server_bootstrap", "")
                done_ev["client_bootstrap"] = build.get("client_bootstrap", "")
            elif build.get("authored"):
                LAST_GAME["prompt"] = prompt
                LAST_GAME["name"] = build.get("name", "game")
                done_ev["authored"] = True
                done_ev["build"] = build.get("build", "")
                done_ev["server"] = build.get("server", "")
                done_ev["client"] = build.get("client", "")
                done_ev["rbxmx"] = build_to_rbxmx(build)
            else:
                done_ev["rbxmx"] = build_to_rbxmx(build)
                for s in build.get("scripts", []):
                    if s.get("name") == "G4Mechanics":
                        done_ev["mechanics"] = s.get("source", "")
                        break
            job["events"].append(done_ev)
        except Exception as ex:
            job["events"].append({"type": "error", "error": str(ex)[:300]})
        finally:
            job["done"] = True

    job["task"] = asyncio.create_task(run())
    # keep the job table from growing unbounded across a long session
    if len(JOBS) > 64:
        for k in [k for k, v in list(JOBS.items())[:32] if v.get("done")]:
            JOBS.pop(k, None)
    return {"job_id": job_id, "root": "G4Game"}


@app.get("/api/generate/poll")
async def gen_poll(job: str, cursor: int = 0):
    j = JOBS.get(job)
    if not j:
        return {"error": "no such job", "done": True, "events": [], "cursor": cursor}
    evs = j["events"][cursor:]
    new_cursor = cursor + len(evs)
    return {"events": evs, "cursor": new_cursor, "done": j["done"] and new_cursor >= len(j["events"])}


@app.websocket("/ws/generate")
async def ws_generate(ws: WebSocket):
    await ws.accept()
    try:
        req = await ws.receive_json()
        prompt = (req.get("prompt") or "").strip()
        if not prompt:
            await ws.send_json({"type": "error", "error": "empty prompt"})
            return

        queue: asyncio.Queue = asyncio.Queue()

        def on_event(e: dict) -> None:
            queue.put_nowait(e)

        async def run() -> None:
            try:
                build, metrics = await generate_game(prompt, on_event=on_event)
                queue.put_nowait({
                    "type": "done",
                    "metrics": metrics,
                    "rbxmx": build_to_rbxmx(build),
                    "luau": build_to_luau(build),
                })
            except Exception as ex:  # surface to the UI rather than dropping the socket
                queue.put_nowait({"type": "error", "error": str(ex)[:300]})
            finally:
                queue.put_nowait({"type": "__end__"})

        task = asyncio.create_task(run())
        while True:
            e = await queue.get()
            if e.get("type") == "__end__":
                break
            await ws.send_json(e)
        await task
    except WebSocketDisconnect:
        pass
    except Exception as ex:
        try:
            await ws.send_json({"type": "error", "error": str(ex)[:300]})
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
