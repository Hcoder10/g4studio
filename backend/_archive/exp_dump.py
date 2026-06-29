import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g4studio.cerebras import CerebrasClient
from g4studio.segmented import run_segmented

async def main():
    client = CerebrasClient()
    try:
        build, m = await run_segmented(
            "a tower defense game with a lobby, waves of enemies that walk a path, buildable towers that shoot enemies, an economy with gold earned per kill, and a HUD showing gold and current wave", client)
        out = os.path.join(os.path.dirname(__file__), "out", "td"); os.makedirs(out, exist_ok=True)
        for s in build.get("shared", []):
            open(os.path.join(out, f"SHARED_{s['name']}.lua"), "w", encoding="utf-8").write(s["source"])
        for s in build.get("systems", []):
            open(os.path.join(out, f"SYS_{s['side']}_{s['name']}.lua"), "w", encoding="utf-8").write(s["source"])
        open(os.path.join(out,"ServerBootstrap.lua"),"w",encoding="utf-8").write(build["server_bootstrap"])
        open(os.path.join(out,"ClientBootstrap.lua"),"w",encoding="utf-8").write(build["client_bootstrap"])
        print("METRICS", m)
        print("REMOTES", build.get("spec",{}).get("shared_remotes"))
        print("FILES", sorted(os.listdir(out)))
    finally:
        await client.aclose()
asyncio.run(main())
