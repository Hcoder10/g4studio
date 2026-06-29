"""Module builders: write ONE focused script per system (the model's strength), all bound
by a fixed architecture CONTRACT so the deterministic integrator can wire them with zero
model guesswork.

Contract:
  - Shared ModuleScripts -> ReplicatedStorage.G4Shared.<Name>   (data/config/util)
  - System ModuleScripts  -> ReplicatedStorage.G4Systems.<Name>  (return { start = function() ... end })
  - RemoteEvents          -> ReplicatedStorage.G4Remotes.<Name>  (created by the server bootstrap)
  - Server systems' start() runs on the server; client systems' on each client.
  - A system NEVER requires another system module (no cycles) — talk via shared modules + remotes.
  - The map/world is built procedurally by the responsible server system in its start().
"""
from __future__ import annotations

import asyncio

from .authored import _force_fix, _strip_fences
from .cerebras import CerebrasClient
from .genre_common import emit_ev

CONTRACT = r"""ARCHITECTURE CONTRACT (follow EXACTLY so the pieces integrate):
- Shared modules live at ReplicatedStorage.G4Shared.<Name>; require via
  require(game:GetService("ReplicatedStorage").G4Shared.<Name>).
- System modules live at ReplicatedStorage.G4Systems.<Name> and MUST return a table with a
  `start` function:  local M = {}  function M.start() ... end  return M
- RemoteEvents are PRE-CREATED by the harness at ReplicatedStorage.G4Remotes.<Name>, ONE per
  name in the SHARED REMOTES list. ALWAYS access them via
  game:GetService("ReplicatedStorage"):WaitForChild("G4Remotes"):WaitForChild("<Name>").
  NEVER create your own RemoteEvent and only use names from the SHARED REMOTES list.
- Do NOT require another SYSTEM module (no cycles). Coordinate ACROSS systems with these shared
  mechanisms (no cross-require needed; they also auto-replicate to clients):
  * per-player state (gold, score, lives): player:SetAttribute("Gold", n) / player:GetAttribute("Gold")
    — the client HUD reads it directly via GetAttribute + player:GetAttributeChangedSignal("Gold"),
    so you usually do NOT need a remote for it.
  * global state (baseHealth, currentWave, gameState): workspace:SetAttribute("BaseHealth", n)
    (readable on the client too).
  * game entities (enemies, pickups): tag each with
    game:GetService("CollectionService"):AddTag(inst, "Enemy"); store per-entity data in attributes
    (inst:SetAttribute("Health", n), inst:SetAttribute("PathProgress", p)); find them with
    CollectionService:GetTagged("Enemy"); give the entity a PrimaryPart for position.
  Use RemoteEvents (from the list) only for explicit client<->server requests/signals.
- SPATIAL DATA is SHARED, never duplicated: the enemy path waypoints, spawn points, buildable
  zones, and the base/goal position live in a shared module — if you need them, READ them from
  there. Do NOT build the map or invent your own path/coordinates unless you ARE the designated
  map/world owner. Two systems using different coordinates is why towers and enemies miss.
- Only REAL Roblox API/Enums; never index a possibly-nil value; never loop without task.wait."""

SHARED_SYSTEM = r"""You are building ONE shared ModuleScript for a Roblox game — it holds data
tables / config / shared utilities that other systems require. Return a ModuleScript:
local M = {} ... return M . Make the data rich and consistent with the game (e.g. a GameConfig
with full tower/enemy/wave definition tables). Follow the contract. Output ONLY the Luau ModuleScript."""

SYSTEM_SYSTEM = r"""You are a senior Roblox engineer building ONE system of a larger game as a
ModuleScript that returns a table with a start() function (called by the bootstrap on the right
side: server or client). Implement the system's responsibility fully and for real — no stubs,
no TODOs. Use the shared modules' actual API (their source is given). If you are the system
responsible for the map/world, build it procedurally in start().

ASSET USAGE — each resolved asset has a TYPE; use it the RIGHT way (the asset line tells you how):
- audio: local s = Instance.new("Sound"); s.SoundId = "rbxassetid://<id>"; s.Parent = part; s:Play().
- decal/image: surfaces -> Instance.new("Decal").Texture = "rbxassetid://<id>"; UI -> imageLabel.Image = it.
- model: it's a full MODEL, NOT a mesh — load it and ALWAYS pcall + fall back to your own primitive:
    local ok, c = pcall(function() return game:GetService("InsertService"):LoadAsset(<numericId>) end)
    if ok and c then local m = c:GetChildren()[1]; if m then m.Parent = parent; m:PivotTo(cf) end
    else --[[ build a primitive version instead ]] end
  Never set MeshId to a model id. Always keep a procedural fallback so the game looks right even if
  an asset fails to load.

GAME FEEL (make it FUN, not a tech demo) — give every important moment FEEDBACK:
- a Sound on key actions (place, shoot, hit, collect, wave start, win, lose);
- a quick visual: a ParticleEmitter:Emit() burst, a TweenService pop/flash/scale, or a Highlight;
- floating number popups for damage/currency (a BillboardGui + TextLabel that rises and fades);
- animate UI with TweenService (never snap); show a clear victory AND defeat screen with payoff.

Follow the contract EXACTLY. Output ONLY the Luau ModuleScript."""


def _asset_use(t: str, aid: str) -> str:
    num = aid.split("//")[-1]
    if t == "audio":
        return f'Sound.SoundId = "{aid}"'
    if t == "decal":
        return f'Decal.Texture (on a part) or ImageLabel.Image (in UI) = "{aid}"'
    if t == "model":
        return f'InsertService:LoadAsset({num}) wrapped in pcall, fall back to your own primitive build'
    return f'"{aid}"'


def _assets_for(sysd: dict, resolved: dict) -> str:
    lines = []
    for q in sysd.get("assets", []) or []:
        hits = resolved.get(q) or []
        if hits:
            h = hits[0]
            lines.append(f'  "{q}" -> {h["name"]} [{h["type"]}]: use as {_asset_use(h["type"], h["id"])}')
    return "\n".join(lines) if lines else "  (none)"


def _spec_header(spec: dict) -> str:
    remotes = ", ".join(spec.get("shared_remotes", []))
    mods = ", ".join(f'{m["name"]} ({m["purpose"]})' for m in spec.get("shared_modules", []))
    return (f'GAME: {spec.get("title")} — {spec.get("summary")}\n'
            f'FLOW: {spec.get("flow")}\nWORLD: {spec.get("world")}\n'
            f'FUN (deliver this hook + reward loop): {spec.get("fun", "")}\n'
            f'DIFFICULTY (escalate like this): {spec.get("difficulty", "")}\n'
            f'SHARED REMOTES: {remotes}\nSHARED MODULES: {mods}')


async def _build_shared(sm: dict, spec: dict, client: CerebrasClient, on_event) -> str:
    aid = f"mod:{sm['name']}"
    emit_ev(on_event, "agent", id=aid, role="Coder", name=sm["name"], status="working")
    user = (f"{_spec_header(spec)}\n\n{CONTRACT}\n\n"
            f"BUILD this shared ModuleScript:\n  name: {sm['name']}\n  purpose: {sm['purpose']}\n"
            f"Return ReplicatedStorage.G4Shared.{sm['name']}.")
    t = await client.chat([{"role": "system", "content": SHARED_SYSTEM},
                           {"role": "user", "content": user}], max_tokens=8000, temperature=0.5)
    emit_ev(on_event, "agent", id=aid, status="done", detail=f"{round(t.tokens_per_sec)} tok/s")
    return _force_fix(_strip_fences(t.text or ""))


async def _build_system(sysd: dict, spec: dict, shared_blob: str, resolved: dict,
                        client: CerebrasClient, on_event) -> str:
    aid = f"sys:{sysd['name']}"
    emit_ev(on_event, "agent", id=aid, role="Coder", name=sysd["name"], status="working")
    user = (f"{_spec_header(spec)}\n\n{CONTRACT}\n\n"
            f"SHARED MODULE SOURCE (use these real APIs):\n{shared_blob}\n\n"
            f"YOUR SYSTEM:\n  name: {sysd['name']}\n  runs on: {sysd['run']}\n"
            f"  responsibility: {sysd['responsibility']}\n"
            f"  resolved assets:\n{_assets_for(sysd, resolved)}\n\n"
            f"Build ReplicatedStorage.G4Systems.{sysd['name']} (returns a table with start()).")
    t = await client.chat([{"role": "system", "content": SYSTEM_SYSTEM},
                           {"role": "user", "content": user}], max_tokens=12000, temperature=0.55)
    emit_ev(on_event, "agent", id=aid, status="done", detail=f"{round(t.tokens_per_sec)} tok/s")
    return _force_fix(_strip_fences(t.text or ""))


async def run_modules(spec: dict, resolved: dict, client: CerebrasClient, on_event=None) -> list[dict]:
    systems = spec.get("systems", [])
    # module-run systems are really shared data/util -> fold into the shared layer
    shared_defs = list(spec.get("shared_modules", []))
    shared_defs += [{"name": s["name"], "purpose": s["responsibility"]}
                    for s in systems if s.get("run") == "module"]
    runnable = [s for s in systems if s.get("run") in ("server", "client")]

    # 1) shared modules first (sequential) so systems can use their real API
    shared_src: dict[str, str] = {}
    for sm in shared_defs:
        if sm["name"] in shared_src:
            continue
        try:
            shared_src[sm["name"]] = await _build_shared(sm, spec, client, on_event)
        except Exception:
            shared_src[sm["name"]] = f"local M = {{}}\nreturn M  -- {sm['name']} (build failed)"
    shared_blob = "\n\n".join(f"-- ReplicatedStorage.G4Shared.{n}\n{s}"
                              for n, s in shared_src.items()) or "(none)"

    # 2) runnable systems in parallel; one failure must not cancel the others or kill the build
    raw = await asyncio.gather(
        *[_build_system(s, spec, shared_blob, resolved, client, on_event) for s in runnable],
        return_exceptions=True)

    modules = [{"name": n, "kind": "shared", "source": s} for n, s in shared_src.items()]
    for sysd, src in zip(runnable, raw):
        if not isinstance(src, str) or len(src) < 50:
            src = f"local M = {{}}\nfunction M.start() end\nreturn M  -- {sysd['name']} (build failed)"
        modules.append({"name": sysd["name"], "kind": sysd["run"], "source": src})
    return modules
