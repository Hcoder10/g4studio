"""Build a full TD game through the segmented harness; verify the contract holds."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from g4studio.cerebras import CerebrasClient
from g4studio.segmented import run_segmented

PROMPT = ("a full tower defense game with a lobby, matchmaking, waves of enemies, "
          "buildable towers, an economy, and a HUD")


async def main():
    client = CerebrasClient()
    try:
        build, m = await run_segmented(PROMPT, client)
        print("METRICS:", m)
        print("SHARED :", [s["name"] for s in build["shared"]])
        print("SYSTEMS:", [(s["name"], s["side"]) for s in build["systems"]])

        problems = []
        for s in build["systems"]:
            src = s["source"]
            if ".start" not in src:
                problems.append(f"{s['name']}: no start()")
            if "return" not in src.split("\n")[-6:][0] and not src.rstrip().endswith(("end", "M", ")")):
                pass
            if "G4Remotes" not in src and s["side"] in ("server", "client") and "remote" in src.lower():
                problems.append(f"{s['name']}: uses remotes but not G4Remotes path")
        print("CONTRACT:", problems or "OK — all systems expose start()")

        # does the server bootstrap reference exactly the server systems?
        srv = [s["name"] for s in build["systems"] if s["side"] == "server"]
        print("BOOTSTRAP server systems:", [n for n in srv if f'"{n}"' in build["server_bootstrap"]],
              "/", srv)

        sysx = max(build["systems"], key=lambda s: len(s["source"]))
        print(f"\n--- LARGEST SYSTEM: {sysx['name']} ({sysx['side']}) "
              f"[{sysx['source'].count(chr(10)) + 1} lines] ---")
        print(sysx["source"][:1400])
    finally:
        await client.aclose()


asyncio.run(main())
