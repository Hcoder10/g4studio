"""Headless check of the plugin streaming path: /api/generate/start then /poll.
Run with the server up:  python backend/poll_test.py
"""
import time
from collections import Counter

import requests

BASE = "http://127.0.0.1:8000"


def main() -> None:
    r = requests.post(BASE + "/api/generate/start",
                      json={"prompt": "neon lava parkour with spinning blades, moving platforms and 2 checkpoints"})
    job = r.json().get("job_id")
    if not job:
        print("no job:", r.text); return
    cursor, done, types, ops = 0, False, [], 0
    t0 = time.time()
    while not done and time.time() - t0 < 40:
        d = requests.get(BASE + "/api/generate/poll", params={"job": job, "cursor": cursor}).json()
        for ev in d.get("events", []):
            types.append(ev["type"])
            if ev["type"] in ("agent_build", "stage"):
                ops += len(ev.get("ops") or [])
            if ev["type"] == "done":
                m = ev.get("metrics", {})
                print("DONE:", {k: m.get(k) for k in
                                ("name", "agents", "parts", "platforms", "hazards", "checkpoints",
                                 "moving", "spinners", "decor", "wall_ms")})
                print(f"  mechanics={len(ev.get('mechanics',''))} bytes, rbxmx={len(ev.get('rbxmx',''))} bytes")
            if ev["type"] == "error":
                print("ERROR:", ev.get("error"))
        cursor, done = d.get("cursor", cursor), d.get("done", False)
        if not done:
            time.sleep(0.1)
    print("events:", dict(Counter(types)))
    print("streamed ops (parts built live in plugin):", ops)
    print("STREAMING OK" if ops > 0 and "done" in types else "WARN")


if __name__ == "__main__":
    main()
