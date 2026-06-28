"""FastAPI server: serves the UI and streams the swarm over a WebSocket.

Run:  python backend/server.py   (then open http://127.0.0.1:8000)
"""
import asyncio
import os
import sys

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(__file__))

from g4studio.swarm import generate_game  # noqa: E402
from g4studio.emit import to_rbxmx, to_luau, to_build  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, "frontend")

app = FastAPI(title="G4 Studio")


@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/generate")
async def api_generate(req: Request):
    """One-shot generate for the Roblox Studio plugin: prompt -> build-ops + metrics.
    Also returns .rbxmx for the no-plugin fallback."""
    body = await req.json()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return {"error": "empty prompt"}
    spec, metrics = await generate_game(prompt)
    return {
        "name": spec.name,
        "metrics": metrics,
        "build": to_build(spec),
        "rbxmx": to_rbxmx(spec),
    }


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


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
                spec, metrics = await generate_game(prompt, on_event=on_event)
                queue.put_nowait({
                    "type": "done",
                    "metrics": metrics,
                    "rbxmx": to_rbxmx(spec),
                    "luau": to_luau(spec),
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
