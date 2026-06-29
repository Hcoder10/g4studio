"""Deterministic integrator + assembler. The integration glue is the model's weakest point,
so we TEMPLATE it: the bootstraps create the remotes and start the systems in order with no
model guesswork. Produces the final build dict the plugin places into Studio services.
"""
from __future__ import annotations


def _lua_list(names) -> str:
    return ", ".join(f'"{n}"' for n in names)


def server_bootstrap(spec: dict, modules: list[dict]) -> str:
    remotes = spec.get("shared_remotes", [])
    server_systems = [m["name"] for m in modules if m["kind"] == "server"]
    return f"""-- G4 Server Bootstrap (auto-generated, deterministic glue)
local RS = game:GetService("ReplicatedStorage")
local rem = RS:FindFirstChild("G4Remotes")
if not rem then rem = Instance.new("Folder"); rem.Name = "G4Remotes"; rem.Parent = RS end
for _, n in ipairs({{{_lua_list(remotes)}}}) do
\tif not rem:FindFirstChild(n) then
\t\tlocal e = Instance.new("RemoteEvent"); e.Name = n; e.Parent = rem
\tend
end
local systems = RS:WaitForChild("G4Systems")
for _, n in ipairs({{{_lua_list(server_systems)}}}) do
\tlocal m = systems:FindFirstChild(n)
\tif m then
\t\tlocal ok, mod = pcall(require, m)
\t\tif ok and type(mod) == "table" and mod.start then
\t\t\tlocal sok, serr = pcall(mod.start)
\t\t\tif not sok then warn("[G4] "..n..".start: "..tostring(serr)) end
\t\telse
\t\t\twarn("[G4] "..n.." has no start()")
\t\tend
\telse
\t\twarn("[G4] server system not found: "..n)
\tend
end
print("[G4] server bootstrap complete")
"""


def client_bootstrap(modules: list[dict]) -> str:
    client_systems = [m["name"] for m in modules if m["kind"] == "client"]
    return f"""-- G4 Client Bootstrap (auto-generated, deterministic glue)
local RS = game:GetService("ReplicatedStorage")
local systems = RS:WaitForChild("G4Systems")
for _, n in ipairs({{{_lua_list(client_systems)}}}) do
\tlocal m = systems:FindFirstChild(n)
\tif m then
\t\tlocal ok, mod = pcall(require, m)
\t\tif ok and type(mod) == "table" and mod.start then pcall(mod.start) end
\tend
end
"""


def assemble(spec: dict, modules: list[dict]) -> dict:
    """Final build the plugin will place:
      shared  -> ReplicatedStorage.G4Shared.<Name>   (ModuleScript)
      systems -> ReplicatedStorage.G4Systems.<Name>  (ModuleScript)
      server_bootstrap -> ServerScriptService.G4ServerBootstrap (Script)
      client_bootstrap -> StarterPlayer.StarterPlayerScripts.G4ClientBootstrap (LocalScript)
    """
    return {
        "segmented": True,
        "name": spec.get("title", "G4 Game"),
        "shared": [{"name": m["name"], "source": m["source"]} for m in modules if m["kind"] == "shared"],
        "systems": [{"name": m["name"], "source": m["source"], "side": m["kind"]}
                    for m in modules if m["kind"] in ("server", "client")],
        "server_bootstrap": server_bootstrap(spec, modules),
        "client_bootstrap": client_bootstrap(modules),
        "spec": spec,
    }
