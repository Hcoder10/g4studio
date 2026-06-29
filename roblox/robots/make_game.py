"""Have Gemma invent a robot-manipulation game and package it -> out/G4RobotGame.rbxmx.

    python roblox/robots/make_game.py ["theme or idea"]

Then insert out/G4RobotGame.rbxmx into Workspace, enable HTTP Requests, and Play.
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))

from g4studio.cerebras import CerebrasClient  # noqa: E402
from g4studio.robotgame import generate_robot_game  # noqa: E402
import build_game_rbxmx as bg  # noqa: E402


async def main():
    theme = sys.argv[1] if len(sys.argv) > 1 else ""
    client = CerebrasClient()
    try:
        g = await generate_robot_game(client, theme)
    finally:
        await client.aclose()
    d = g["design"]
    path = bg.build(g["source"])
    print(f"\n  {d['name']}  —  {d['pitch']}")
    print(f"  skill: {d['skill']}")
    print(f"  task : {d['task']}   compiles: {g['compiles']}   ({g['source'].count(chr(10)) + 1} lines)")
    print(f"  -> {path}\n  Insert into Workspace, enable HTTP, Play. Traces -> /api/datasets")


if __name__ == "__main__":
    asyncio.run(main())
