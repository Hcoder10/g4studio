import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g4studio.swarm import generate_game

async def main():
    build, m = await generate_game("a full tower defense game with lobby, matchmaking, waves of enemies, buildable towers, an economy, and a HUD")
    print("COMPLEX -> genre:", m.get("genre"), "| segmented:", build.get("segmented"), "| name:", build.get("name"))
    print("  shared :", [s["name"] for s in build.get("shared", [])])
    print("  systems:", [(s["name"], s["side"]) for s in build.get("systems", [])])
    print("  bootstraps: server", bool(build.get("server_bootstrap")), "client", bool(build.get("client_bootstrap")))
    b2, m2 = await generate_game("a simple lava obby where you jump across platforms to the top")
    print("SIMPLE  -> genre:", m2.get("genre"), "| authored:", b2.get("authored"))

asyncio.run(main())
