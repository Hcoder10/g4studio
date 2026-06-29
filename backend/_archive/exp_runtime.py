import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g4studio.cerebras import CerebrasClient
from g4studio.runtime import repair_runtime_errors

modules = [{"name": "TowerSystem", "kind": "server",
            "source": 'local M = {}\nfunction M.start()\n\tlocal t = workspace.Towers\n\tprint(t.Count)\nend\nreturn M'}]
errors = [{"message": "Towers is not a valid member of Workspace \"Workspace\"",
           "script": "ReplicatedStorage.G4Systems.TowerSystem", "trace": "TowerSystem.start:3"}]

async def main():
    c = CerebrasClient()
    try:
        fixed = await repair_runtime_errors(modules, errors, c)
        print("fixed modules:", [f["name"] for f in fixed])
        if fixed:
            print("--- repaired TowerSystem ---")
            print(fixed[0]["source"][:400])
    finally:
        await c.aclose()
asyncio.run(main())
