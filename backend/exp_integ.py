import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g4studio.cerebras import CerebrasClient
from g4studio.architect import run_architect, resolve_assets
from g4studio.builder import run_modules
from g4studio import integration

async def main():
    client = CerebrasClient()
    reviews = []
    orig = client.structured
    async def cap(system, user, schema, **kw):
        out, turn = await orig(system, user, schema, **kw)
        if kw.get("name") == "integration_review": reviews.append(out)
        return out, turn
    client.structured = cap
    try:
        spec, _ = await run_architect("a tower defense game with waves of enemies, towers that shoot them, a gold economy, and a HUD", client)
        modules = await run_modules(spec, resolve_assets(spec, k=2), client)
        await integration.run_integration_qa(spec, modules, client)
        if reviews:
            r = reviews[0]
            print("=== CONVENTIONS ===")
            print(r.get("conventions", "")[:2200])
            print("\n=== FIXES (%d) ===" % len(r.get("fixes", [])))
            for f in r.get("fixes", []):
                print(f"- {f['module']}: {f['problem'][:90]}")
    finally:
        await client.aclose()
asyncio.run(main())
