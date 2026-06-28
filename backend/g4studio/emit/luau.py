"""Emit a GameSpec as a command-bar Luau build script (fallback artifact).

Paste into Studio's command bar (edit mode) to construct the obby live. Useful if
.rbxmx insertion is unavailable. The command bar runs with elevated permissions,
so setting Script.Source works here.
"""
from __future__ import annotations

from ..mechanics import get_mechanics_luau
from ..ops import GameSpec
from .common import hex_to_rgb


def _mk(folder: str, name: str, pos, size, color: str, material: str,
        class_name: str = "Part") -> str:
    r, g, b = hex_to_rgb(color)
    return (
        f'do local p=Instance.new("{class_name}");p.Name="{name}";p.Anchored=true;'
        f'p.Size=Vector3.new({size[0]},{size[1]},{size[2]});'
        f'p.CFrame=CFrame.new({pos[0]},{pos[1]},{pos[2]});'
        f'p.Color=Color3.fromRGB({r},{g},{b});p.Material=Enum.Material.{material};'
        f'p.Parent={folder} end'
    )


def to_luau(spec: GameSpec) -> str:
    L = []
    L.append(f"-- G4Studio generated obby: {spec.name}")
    L.append("local WS = workspace")
    L.append('local old = WS:FindFirstChild("G4Obby"); if old then old:Destroy() end')
    L.append('local root = Instance.new("Folder"); root.Name = "G4Obby"; root.Parent = WS')
    for f in ("Platforms", "Hazards", "Checkpoints", "Moving"):
        L.append(f'local {f} = Instance.new("Folder"); {f}.Name = "{f}"; {f}.Parent = root')

    for i, p in enumerate(spec.platforms):
        L.append(_mk("Platforms", f"Platform{i + 1}", p.pos, p.size, p.color, p.material))
    for i, h in enumerate(spec.hazards):
        L.append(_mk("Hazards", f"Hazard{i + 1}", h.pos, h.size, h.color, h.material))
    for c in spec.checkpoints:
        L.append(_mk("Checkpoints", f"Checkpoint{c.index}", c.pos, c.size, c.color, c.material))
    for m in spec.moving:
        L.append(_mk("Moving", f"Move_{m.axis}_{m.distance}_{m.speed}", m.pos, m.size, m.color, m.material))

    L.append(_mk("root", "Spawn", spec.spawn.pos, (8.0, 1.0, 8.0), "#cfd8dc", "SmoothPlastic",
                 class_name="SpawnLocation"))
    L.append(_mk("root", "Win", spec.win.pos, spec.win.size, spec.win.color, spec.win.material))

    mech = get_mechanics_luau().replace("]==]", "]= =]")
    L.append('local mech = Instance.new("Script"); mech.Name = "G4Mechanics"')
    L.append(f"mech.Source = [==[\n{mech}\n]==]")
    L.append("mech.Parent = root")
    L.append(f'print("[G4Studio] Built obby: {spec.name} (" .. #root.Platforms:GetChildren() .. " platforms)")')
    return "\n".join(L)
