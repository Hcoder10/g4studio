import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g4studio.cerebras import CerebrasClient
from g4studio.authored import run_authored
async def main():
    c = CerebrasClient()
    try:
        build, m = await run_authored(
            "a tower defense game with a short lobby countdown, waves of enemies that walk a path to your base, towers you place with your mouse that shoot the enemies, a gold economy (earn gold per kill, spend to place towers), and a HUD showing gold/wave/base health", c)
        out = "out/auth"; os.makedirs(out, exist_ok=True)
        for k in ("build","server","client"):
            open(f"{out}/{k}.lua","w",encoding="utf-8").write(build.get(k,""))
        print("NAME:", build.get("name"))
        for k in ("build","server","client"):
            s = build.get(k,""); print(f"  {k}: {s.count(chr(10))+1} lines")
    finally:
        await c.aclose()
asyncio.run(main())
