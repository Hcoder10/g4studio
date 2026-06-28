"""End-to-end: prompt -> Gemma-4 swarm -> playable Roblox artifacts.

Run:  python backend/generate.py "neon lava parkour with moving platforms"
Out:  out/g4obby.rbxmx  +  out/g4obby_build.luau
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from g4studio.swarm import generate_game  # noqa: E402
from g4studio.emit import build_to_rbxmx, build_to_luau  # noqa: E402


def on_event(e: dict) -> None:
    t = e.get("type")
    if t == "genre":
        print(f"  [router] genre = {e.get('genre')}")
    elif t == "director_started":
        print("  [director] designing the game...")
    elif t == "director_done":
        print(f"  [director] '{e.get('name')}' - {e.get('stages')} stages "
              f"({e.get('tps')} tok/s, {e.get('ms')} ms)")
    elif t == "builder_started":
        print(f"  [builder {e.get('stage')}] building '{e.get('name')}'...")
    elif t == "builder_done":
        c = e.get("counts", {})
        print(f"  [builder {e.get('stage')}] done: {c}  ({e.get('tps')} tok/s, {e.get('ms')} ms)")
    elif t == "builder_error":
        print(f"  [builder {e.get('stage')}] ERROR: {e.get('error')}")
    elif t == "assembled":
        print(f"  [assembled] {e.get('parts')} parts in {e.get('wall_ms')} ms")


async def main() -> None:
    prompt = " ".join(sys.argv[1:]) or "neon lava parkour with moving platforms and 2 checkpoints"
    print(f"\nPrompt: {prompt}\n")
    t0 = time.perf_counter()
    build, metrics = await generate_game(prompt, on_event=on_event)
    wall = (time.perf_counter() - t0) * 1000

    out_dir = os.path.join(os.path.dirname(__file__), "..", "out")
    os.makedirs(out_dir, exist_ok=True)
    rbxmx_path = os.path.join(out_dir, "g4obby.rbxmx")
    luau_path = os.path.join(out_dir, "g4obby_build.luau")
    with open(rbxmx_path, "w", encoding="utf-8") as f:
        f.write(build_to_rbxmx(build))
    with open(luau_path, "w", encoding="utf-8") as f:
        f.write(build_to_luau(build))

    print("\n=== RESULT ===")
    extra = " ".join(f"{k}={metrics[k]}" for k in
                     ("platforms", "hazards", "checkpoints", "moving", "spinners", "decor",
                      "zones", "orbs", "upgrades") if k in metrics)
    print(f"  [{metrics.get('genre')}] {metrics.get('name')}: {metrics.get('parts')} parts  {extra}")
    print(f"  {metrics.get('agents')} agents, {metrics.get('completion_tokens')} tokens, "
          f"per-agent tok/s={metrics.get('agent_tps')}")
    print(f"  TOTAL WALL TIME: {wall:.0f} ms")
    print(f"  wrote {os.path.abspath(rbxmx_path)}")
    print(f"  wrote {os.path.abspath(luau_path)}")
    print("\n  In Studio: right-click Workspace -> Insert From File -> g4obby.rbxmx -> Play")


if __name__ == "__main__":
    asyncio.run(main())
