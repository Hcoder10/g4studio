import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g4studio.cerebras import CerebrasClient
from g4studio.segmented import run_segmented
from g4studio.verify import verify

async def main():
    client = CerebrasClient()
    try:
        build, m = await run_segmented(
            "a tower defense game with waves of enemies that walk a path, towers that shoot them, a gold economy earning gold per kill, and a HUD showing gold and wave", client)
        spec = build["spec"]
        modules = [{"name": s["name"], "kind": "shared", "source": s["source"]} for s in build["shared"]]
        modules += [{"name": s["name"], "kind": s["side"], "source": s["source"]} for s in build["systems"]]
        issues, remotes = verify(spec, modules)
        print("METRICS:", {k: m[k] for k in ("name","systems","shared","lines","wall_ms")})
        print("shared_remotes (after union):", spec.get("shared_remotes"))
        print("REMAINING MISMATCHES:", len(issues))
        for i in issues:
            print("  -", i["detail"][:150])
    finally:
        await client.aclose()
asyncio.run(main())
