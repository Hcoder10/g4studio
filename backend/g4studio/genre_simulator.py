"""Simulator genre: collect orbs -> sell for Coins -> buy upgrades.

Director designs a hub + themed zones; one Builder per zone places the zone's
platform, orbs, and decorations (in parallel). A templated economy mechanics
script (with a baked CONFIG of orb values + upgrade costs) wires the loop.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from .cerebras import CerebrasClient
from .genre_common import VEC3, emit_ev, lua_value, op, xyz

_HEX = {"type": "string"}

SIM_DIRECTOR_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "theme": {"type": "string"},
        "palette": {"type": "array", "items": {"type": "string"}},
        "base": {"type": "object", "additionalProperties": False,
                 "properties": {"pos": VEC3, "size": VEC3, "color": _HEX},
                 "required": ["pos", "size", "color"]},
        "sell": {"type": "object", "additionalProperties": False,
                 "properties": {"pos": VEC3, "color": _HEX}, "required": ["pos", "color"]},
        "zones": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"name": {"type": "string"}, "center": VEC3,
                           "orb_color": _HEX, "orb_value": {"type": "number"},
                           "platform_color": _HEX},
            "required": ["name", "center", "orb_color", "orb_value", "platform_color"]}},
        "upgrades": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"pos": VEC3, "kind": {"type": "string", "enum": ["capacity", "multiplier"]},
                           "cost": {"type": "number"}, "color": _HEX},
            "required": ["pos", "kind", "cost", "color"]}},
    },
    "required": ["name", "theme", "palette", "base", "sell", "zones", "upgrades"],
}

SIM_ZONE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "platforms": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"pos": VEC3, "size": VEC3, "color": _HEX},
            "required": ["pos", "size", "color"]}},
        "orbs": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"pos": VEC3}, "required": ["pos"]}},
        "decorations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"pos": VEC3, "size": VEC3, "color": _HEX},
            "required": ["pos", "size", "color"]}},
    },
    "required": ["platforms", "orbs", "decorations"],
}

SIM_DIRECTOR_SYSTEM = """You are the lead designer of an automated Roblox SIMULATOR studio
(the genre where players walk around collecting glowing orbs, sell them for Coins, and buy
upgrades — like Bubble Gum / Pet Simulator).

Design a complete world. Rules:
- `base`: a large flat floor near the origin (e.g. pos {x:0,y:0,z:0}, size {x:120,y:2,z:120}).
- `sell`: a Sell pad ON the base near spawn (y just above the base top).
- `zones`: 3 to 5 themed collection areas spread out around the base at different x/z (40-90
  studs away). Each has an `orb_color` (hex) and an `orb_value` (further/cooler zones worth more:
  1, 2, 5, 10, 25). Give each a `platform_color`.
- `upgrades`: 2 to 3 upgrade pads near the base (kind "capacity" = carry more, "multiplier" =
  worth more), with increasing `cost` (50, 150, 400). Hex colors.
- All colors hex. Coordinates in studs, Y up. Make it feel like a real game."""

SIM_ZONE_SYSTEM = """You are a BUILDER agent building ONE collection zone of a Roblox simulator.
Given the zone center, theme, and colors, output strict JSON:
- platforms: 1-3 parts forming a small island/area around the center (e.g. an 30x2x30 floor at
  the center, maybe a raised tier). Use platform_color.
- orbs: 10 to 20 collectible orb positions, scattered ABOVE the platform surface (y = platform
  top + 2 to 4), spread across the zone. Just positions; the orb color/value is applied for you.
- decorations: 3-6 non-blocking themed props (pillars, crystals) beside the area.
Use ABSOLUTE world coordinates near the given center. All colors hex."""

SIM_BODY = r"""
local Players = game:GetService("Players")
local root = script.Parent

local function onPlayer(plr)
    local ls = Instance.new("Folder"); ls.Name = "leaderstats"; ls.Parent = plr
    local coins = Instance.new("IntValue"); coins.Name = "Coins"; coins.Parent = ls
    local carry = Instance.new("IntValue"); carry.Name = "Carrying"; carry.Parent = ls
    plr:SetAttribute("Cap", CONFIG.startCap or 15)
    plr:SetAttribute("Mult", 1)
end
Players.PlayerAdded:Connect(onPlayer)
for _, p in ipairs(Players:GetPlayers()) do onPlayer(p) end

local orbs = root:FindFirstChild("Orbs")
if orbs then
    for _, orb in ipairs(orbs:GetChildren()) do
        if orb:IsA("BasePart") then
            local val = CONFIG.orbs[orb.Name] or 1
            orb.Touched:Connect(function(hit)
                if orb.Transparency > 0 then return end
                local plr = Players:GetPlayerFromCharacter(hit.Parent)
                if not plr then return end
                local ls = plr:FindFirstChild("leaderstats"); if not ls then return end
                local cap = plr:GetAttribute("Cap") or 15
                if ls.Carrying.Value >= cap then return end
                ls.Carrying.Value = math.min(ls.Carrying.Value + val, cap)
                orb.Transparency = 1; orb.CanTouch = false
                task.delay(4, function()
                    if orb and orb.Parent then orb.Transparency = 0; orb.CanTouch = true end
                end)
            end)
        end
    end
end

local sell = root:FindFirstChild("SellPad")
if sell then
    sell.Touched:Connect(function(hit)
        local plr = Players:GetPlayerFromCharacter(hit.Parent)
        if not plr then return end
        local ls = plr:FindFirstChild("leaderstats"); if not ls then return end
        if ls.Carrying.Value > 0 then
            ls.Coins.Value += ls.Carrying.Value * (plr:GetAttribute("Mult") or 1)
            ls.Carrying.Value = 0
        end
    end)
end

local ups = root:FindFirstChild("Upgrades")
if ups then
    for _, pad in ipairs(ups:GetChildren()) do
        if pad:IsA("BasePart") then
            local cfg = CONFIG.upgrades[pad.Name] or { kind = "capacity", cost = 50 }
            pad.Touched:Connect(function(hit)
                local plr = Players:GetPlayerFromCharacter(hit.Parent)
                if not plr then return end
                local ls = plr:FindFirstChild("leaderstats"); if not ls then return end
                if ls.Coins.Value >= cfg.cost then
                    ls.Coins.Value -= cfg.cost
                    if cfg.kind == "multiplier" then
                        plr:SetAttribute("Mult", (plr:GetAttribute("Mult") or 1) + 1)
                    else
                        plr:SetAttribute("Cap", (plr:GetAttribute("Cap") or 15) + 15)
                    end
                end
            end)
        end
    end
end

print("[G4Studio] simulator online")
"""


async def _zone_builder(client: CerebrasClient, idx: int, zone: dict, theme: str, cb) -> dict:
    name = zone.get("name", f"Zone {idx + 1}")
    emit_ev(cb, "builder_started", stage=idx, name=name)
    user = (f"Zone: {name}\nTheme: {theme}\nCenter: {zone.get('center')}\n"
            f"Platform color: {zone.get('platform_color')}\nBuild this zone now.")
    try:
        out, turn = await client.structured(SIM_ZONE_SYSTEM, user, SIM_ZONE_SCHEMA,
                                            name="zone", max_tokens=5000, temperature=0.6)
    except Exception as e:
        emit_ev(cb, "builder_error", stage=idx, error=str(e)[:200])
        return {"ops": [], "orbs": {}, "turn": None}

    ops, orb_cfg = [], {}
    pcolor = zone.get("platform_color", "#6c5ce7")
    ocolor = zone.get("orb_color", "#00e5ff")
    oval = int(zone.get("orb_value", 1))
    for i, p in enumerate(out.get("platforms") or []):
        ops.append(op("Zones", f"Z{idx}_P{i + 1}", p.get("pos"), p.get("size") or (24, 2, 24),
                      p.get("color", pcolor), "SmoothPlastic"))
    for i, o in enumerate(out.get("orbs") or []):
        nm = f"Orb_{idx}_{i + 1}"
        ops.append(op("Orbs", nm, o.get("pos"), (1.6, 1.6, 1.6), ocolor, "Neon"))
        orb_cfg[nm] = oval
    for i, d in enumerate(out.get("decorations") or []):
        ops.append(op("Decor", f"Z{idx}_D{i + 1}", d.get("pos"), d.get("size") or (2, 10, 2),
                      d.get("color", pcolor), "Neon", cc=False))

    counts = {"platforms": len(out.get("platforms") or []), "orbs": len(out.get("orbs") or []),
              "decorations": len(out.get("decorations") or [])}
    emit_ev(cb, "builder_done", stage=idx, name=name, counts=counts, ops=ops,
            tokens=turn.completion_tokens, tps=round(turn.tokens_per_sec), ms=round(turn.latency_ms))
    return {"ops": ops, "orbs": orb_cfg, "turn": turn}


async def run_simulator(prompt: str, client: CerebrasClient, on_event=None,
                        feedback=None) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    turns = []
    emit_ev(on_event, "director_started")
    director_user = prompt if not feedback else \
        prompt + "\n\nREDESIGN FEEDBACK (the playtester rejected your last attempt — fix these): " + feedback
    design, dturn = await client.structured(SIM_DIRECTOR_SYSTEM, director_user, SIM_DIRECTOR_SCHEMA,
                                            name="sim_design", max_tokens=3500, temperature=0.5)
    turns.append(dturn)
    name = design.get("name", "Collect Quest")
    theme = design.get("theme", "")
    zones = design.get("zones") or []
    emit_ev(on_event, "director_done", name=name, theme=theme, stages=len(zones),
            tokens=dturn.completion_tokens, tps=round(dturn.tokens_per_sec), ms=round(dturn.latency_ms))

    base = design.get("base") or {}
    base_pos = xyz(base.get("pos"), (0, 0, 0))
    base_size = xyz(base.get("size"), (120, 2, 120))
    sell = design.get("sell") or {}
    spawn_pos = [base_pos[0], base_pos[1] + base_size[1] / 2 + 3, base_pos[2]]

    parts = [
        op("Base", "Floor", base_pos, base_size, base.get("color", "#2d3436"), "Concrete"),
        op("_root", "SellPad", sell.get("pos") or [base_pos[0], spawn_pos[1], base_pos[2] + 14],
           (10, 1, 10), sell.get("color", "#39d353"), "Neon"),
        op("_root", "Spawn", spawn_pos, (8, 1, 8), "#cfd8dc", "SmoothPlastic", klass="SpawnLocation"),
    ]
    config = {"startCap": 15, "orbs": {}, "upgrades": {}}
    for i, u in enumerate(design.get("upgrades") or []):
        nm = f"Up_{i + 1}"
        parts.append(op("Upgrades", nm, u.get("pos"), (6, 1, 6), u.get("color", "#ffd400"), "Neon"))
        config["upgrades"][nm] = {"kind": u.get("kind", "capacity"), "cost": int(u.get("cost", 50))}

    # Emit the hub frame first so it appears immediately in the live build.
    emit_ev(on_event, "stage", ops=list(parts))

    results = await asyncio.gather(*[
        _zone_builder(client, i, z, theme, on_event) for i, z in enumerate(zones)
    ])
    for r in results:
        parts.extend(r["ops"])
        config["orbs"].update(r["orbs"])
        if r["turn"] is not None:
            turns.append(r["turn"])

    mechanics = f"--!nonstrict\nlocal CONFIG = {lua_value(config)}\n{SIM_BODY}"
    folders = ["Base", "Zones", "Orbs", "Upgrades", "Decor"]
    build = {
        "root": "G4Game", "name": name, "folders": folders, "parts": parts,
        "scripts": [{"folder": "_root", "name": "G4Mechanics", "source": mechanics}],
    }
    wall_ms = (time.perf_counter() - t0) * 1000.0
    orbs = sum(1 for p in parts if p["folder"] == "Orbs")
    metrics = {
        "genre": "simulator", "name": name, "agents": 1 + len(zones),
        "wall_ms": round(wall_ms), "parts": len(parts),
        "completion_tokens": sum(t.completion_tokens for t in turns),
        "agent_tps": [round(t.tokens_per_sec) for t in turns],
        "zones": len(zones), "orbs": orbs, "upgrades": len(config["upgrades"]),
    }
    emit_ev(on_event, "assembled", parts=len(parts), wall_ms=round(wall_ms))
    return build, metrics
