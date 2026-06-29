"""Verify the Architect generalizes across game types + resolves assets via the RAG."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from g4studio.architect import resolve_assets, run_architect
from g4studio.cerebras import CerebrasClient

PROMPTS = [
    "a full tower defense game with a lobby, matchmaking, waves of enemies, buildable towers, an economy, and a HUD",
    "a simple obby where you jump across platforms to reach the top",
    "a racing game where players race cars around a track for 3 laps",
]


async def main():
    client = CerebrasClient()
    try:
        for p in PROMPTS:
            spec, turn = await run_architect(p, client)
            print("\n" + "=" * 72)
            print("PROMPT:", p[:64])
            print("TITLE:", spec.get("title"), "| FLOW:", spec.get("flow"))
            print("remotes:", spec.get("shared_remotes"))
            print("modules:", [m.get("name") for m in spec.get("shared_modules", [])])
            print("SYSTEMS (%d):" % len(spec.get("systems", [])))
            for s in spec.get("systems", []):
                print(f"  - [{s.get('run'):6}] {s.get('name')}: {str(s.get('responsibility'))[:64]}")
                if s.get("assets"):
                    print(f"        assets: {s.get('assets')}")
            assets = resolve_assets(spec, k=2)
            if assets:
                print("RESOLVED (RAG):")
                for q, hits in list(assets.items())[:10]:
                    print(f"  {q!r} -> " + ", ".join(f"{h['name']}({h['score']})" for h in hits))
    finally:
        await client.aclose()


asyncio.run(main())
