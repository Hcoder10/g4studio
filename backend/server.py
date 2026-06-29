"""FastAPI server: serves the UI and streams the swarm over a WebSocket.

Run:  python backend/server.py   (then open http://127.0.0.1:8000)
"""
import asyncio
import json
import os
import sys
import time
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


# ---- robot manipulation traces (the data the games collect) ----
DATASET_DIR = os.path.join(REPO, "datasets")


@app.post("/api/trace")
async def api_trace(req: Request):
    """Store one manipulation episode (obs/action/reward/sub-goal per step) as a dataset line.
    One .jsonl per task; this is the training data the gamified sims naturally produce."""
    ep = await req.json()
    if not ep.get("steps"):
        return {"ok": False, "error": "empty episode"}
    os.makedirs(DATASET_DIR, exist_ok=True)
    task = "".join(c for c in str(ep.get("task") or "task") if c.isalnum() or c in "_-")[:60] or "task"
    ep["received_at"] = time.time()
    path = os.path.join(DATASET_DIR, f"{task}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(ep) + "\n")
    n = sum(1 for _ in open(path, encoding="utf-8"))
    return {"ok": True, "task": task, "length": ep.get("length"),
            "success": ep.get("success"), "episodes_for_task": n}


@app.get("/api/datasets")
async def api_datasets():
    """Summary of collected episodes per task."""
    out = {}
    if os.path.isdir(DATASET_DIR):
        for fn in os.listdir(DATASET_DIR):
            if fn.endswith(".jsonl"):
                p = os.path.join(DATASET_DIR, fn)
                eps = [json.loads(ln) for ln in open(p, encoding="utf-8") if ln.strip()]
                out[fn[:-6]] = {
                    "episodes": len(eps),
                    "successes": sum(1 for e in eps if e.get("success")),
                    "total_steps": sum(int(e.get("length", 0)) for e in eps),
                }
    return out


def _build_robot_game(source: str) -> str:
    """Package a Gemma-authored Game module + the kit into out/G4RobotGame.rbxmx; return the path."""
    import importlib.util
    bgpath = os.path.join(REPO, "roblox", "robots", "build_game_rbxmx.py")
    spec = importlib.util.spec_from_file_location("g4_build_game", bgpath)
    bg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bg)
    return bg.build(source, os.path.join(REPO, "out", "G4RobotGame.rbxmx"))


@app.post("/api/robotgame")
async def api_robotgame(req: Request):
    """Gemma designs + codes a fun robot-manipulation game (data falls out of play) and we package
    it with the kit into out/G4RobotGame.rbxmx."""
    from g4studio.robotgame import generate_robot_game
    body = await req.json()
    theme = (body.get("theme") or "").strip()
    client = CerebrasClient()
    try:
        g = await generate_robot_game(client, theme)
    finally:
        await client.aclose()
    path = _build_robot_game(g["source"])
    return {"design": g["design"], "compiles": g["compiles"],
            "lines": g["source"].count("\n") + 1, "rbxmx": path}


@app.get("/api/robotgame/file")
async def api_robotgame_file():
    return FileResponse(os.path.join(REPO, "out", "G4RobotGame.rbxmx"), filename="G4RobotGame.rbxmx")


@app.post("/api/robotgame/extend")
async def api_robotgame_extend(req: Request):
    """A running game calls this once the player has MASTERED it; Gemma forges the next, harder
    challenge and returns its Luau source for the game to hot-swap (loadstring) in place."""
    from g4studio.robotgame import extend_robot_game
    body = await req.json()
    prev = {"name": body.get("name", "game"), "task": body.get("task", ""), "skill": body.get("skill", "")}
    stats = {"wins": body.get("wins", 0), "avg_seconds": body.get("avg_seconds")}
    client = CerebrasClient()
    try:
        g = await extend_robot_game(client, prev, stats)
    finally:
        await client.aclose()
    return {"design": g["design"], "compiles": g["compiles"], "source": g["source"]}


# ---- AI playtester that actually PLAYS the game in a real Play session ----
LAST_GAME = {"prompt": "", "name": ""}
LAST_BUILD = {"spec": {}, "modules": []}  # last segmented build, for the runtime-error oracle
PLAYBOT = {"notes": []}


@app.post("/api/runtime_repair")
async def api_runtime_repair(req: Request):
    """Play-test oracle: the plugin ran the game and captured runtime errors; repair the
    offending modules and return the fixed sources for the plugin to re-place + re-run."""
    body = await req.json()
    errors = body.get("errors") or []
    if not errors or not LAST_BUILD.get("modules"):
        return {"fixed": []}
    from g4studio.runtime import repair_runtime_errors
    client = CerebrasClient()
    try:
        fixed = await repair_runtime_errors(LAST_BUILD["modules"], errors, client)
        return {"fixed": fixed}
    finally:
        await client.aclose()

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


MAP_REVISE_SYSTEM = (
    "You are improving the WORLD/MAP-building code of one Roblox module. A playtester saw the map "
    "running in-game and gave feedback. Make the map richer and clearer per the feedback — denser "
    "decoration, a clearly bounded arena, a readable enemy path, good lighting/atmosphere — WITHOUT "
    "changing gameplay logic or any shared coordinates/waypoints/spawn points. Only REAL Roblox API. "
    "Output ONLY the corrected Luau module.")


@app.post("/api/map_vision")
async def api_map_vision(req: Request):
    """Vision map QA for a running segmented game: screenshot Studio, grade the MAP, and if weak
    revise the map-owning module (the one that builds the most world geometry)."""
    data_uri = capture_data_uri()
    if not data_uri or not LAST_BUILD.get("modules"):
        return {"score": 7, "issues": [], "fixed": []}
    client = CerebrasClient()
    try:
        crit, _ = await client.vision_json(
            PLAYTEST_OPEN,
            "This is a screenshot of an auto-generated game's MAP/arena running in Studio. Grade the "
            "MAP quality (layout, decoration density, clarity of the playable area + path, atmosphere). "
            "Output only JSON.", data_uri, max_tokens=1000)
        try:
            score = int(crit.get("score", 7))
        except (TypeError, ValueError):
            score = 7
        issues = [str(x) for x in (crit.get("issues") or [])][:4]
        if score >= 6:
            return {"score": score, "issues": issues, "fixed": []}
        modules = LAST_BUILD["modules"]
        owner = max(modules, key=lambda m: m["source"].count('Instance.new("Part"'))
        if owner["source"].count('Instance.new("Part"') < 3:
            return {"score": score, "issues": issues, "fixed": []}
        rv = await client.chat(
            [{"role": "system", "content": MAP_REVISE_SYSTEM},
             {"role": "user", "content":
              f"Playtester saw the map and scored it {score}/10. Issues: {'; '.join(issues)}. "
              f"Improve the MAP-building in this module (keep gameplay + shared coordinates):\n{owner['source']}"}],
            max_tokens=12000, temperature=0.5)
        fixed_src = _force_fix(_strip_fences(rv.text or ""))
        if len(fixed_src) > 200:
            owner["source"] = fixed_src
            return {"score": score, "issues": issues,
                    "fixed": [{"name": owner["name"], "kind": owner["kind"], "source": fixed_src}]}
        return {"score": score, "issues": issues, "fixed": []}
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
        if score < 6 and attempt < 3 and len(build_src) > 50:
            rv = await client.chat(
                [{"role": "system", "content": REVISE_SYSTEM},
                 {"role": "user", "content":
                  f"A playtester saw the level in Studio and scored it {score}/10. FIX EACH ISSUE THEY "
                  f"RAISED: {'; '.join(issues) or verdict}. Rewrite the BUILD to specifically address "
                  f"them — dense decoration (dozens of props via loops), a clearly bounded arena with "
                  f"real structure + lighting/atmosphere; keep the same theme and any coordinates/"
                  f"waypoints/folders the gameplay relies on. BUILD code:\n{build_src}"}],
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
                LAST_BUILD["spec"] = build.get("spec", {})
                LAST_BUILD["modules"] = (
                    [{"name": s["name"], "kind": "shared", "source": s["source"]}
                     for s in build.get("shared", [])]
                    + [{"name": s["name"], "kind": s["side"], "source": s["source"]}
                       for s in build.get("systems", [])])
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
