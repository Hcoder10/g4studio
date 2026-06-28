"""Headless check of the server's WebSocket pipeline (no browser needed).

Connects to /ws/generate, sends a prompt, and verifies the full event stream
(director -> parallel builders with build-ops -> done + artifacts).
Run with the server up:  python backend/ws_test.py
"""
import asyncio
import json
from collections import Counter

import websockets


async def main() -> None:
    uri = "ws://127.0.0.1:8000/ws/generate"
    async with websockets.connect(uri, max_size=16 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"prompt": "icy mountain climb with moving platforms and 2 checkpoints"}))
        types = []
        streamed_parts = 0
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=40)
            e = json.loads(msg)
            t = e.get("type")
            types.append(t)
            if t == "builder_done":
                els = e.get("elements") or {}
                streamed_parts += sum(len(els.get(k, []) or []) for k in
                                      ("platforms", "hazards", "checkpoints", "moving"))
            elif t == "done":
                m = e.get("metrics", {})
                print("DONE:", {k: m.get(k) for k in ("name", "agents", "parts", "wall_ms")})
                print(f"  rbxmx={len(e.get('rbxmx',''))} bytes, luau={len(e.get('luau',''))} bytes")
                break
            elif t == "error":
                print("ERROR:", e.get("error"))
                return
        print("event sequence:", dict(Counter(types)))
        print("streamed build-op parts (for live 3D render):", streamed_parts)
        print("PIPELINE OK" if streamed_parts > 0 else "WARN: no parts streamed")


if __name__ == "__main__":
    asyncio.run(main())
