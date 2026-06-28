"""Emit a GameSpec as a flat build-op list the Studio plugin applies live.

Generic ops (folder/part/script) keep the plugin dumb: it just creates instances
and sets properties. The server owns all the translation. Same templated mechanics
as the .rbxmx path, so behaviour is identical whether built live or inserted.
"""
from __future__ import annotations

from ..mechanics import get_mechanics_luau
from ..ops import GameSpec
from .common import hex_to_rgb


def _part(folder: str, class_name: str, name: str, pos, size, color: str, material: str) -> dict:
    r, g, b = hex_to_rgb(color)
    return {
        "folder": folder,
        "class": class_name,
        "name": name,
        "pos": [round(pos[0], 2), round(pos[1], 2), round(pos[2], 2)],
        "size": [round(size[0], 2), round(size[1], 2), round(size[2], 2)],
        "color": [r, g, b],
        "material": material,
    }


def to_build(spec: GameSpec) -> dict:
    parts = []
    for i, p in enumerate(spec.platforms):
        parts.append(_part("Platforms", "Part", f"Platform{i + 1}", p.pos, p.size, p.color, p.material))
    for i, h in enumerate(spec.hazards):
        parts.append(_part("Hazards", "Part", f"Hazard{i + 1}", h.pos, h.size, h.color, h.material))
    for c in spec.checkpoints:
        parts.append(_part("Checkpoints", "Part", f"Checkpoint{c.index}", c.pos, c.size, c.color, c.material))
    for m in spec.moving:
        parts.append(_part("Moving", "Part", f"Move_{m.axis}_{m.distance}_{m.speed}",
                           m.pos, m.size, m.color, m.material))
    parts.append(_part("_root", "SpawnLocation", "Spawn", spec.spawn.pos, (8, 1, 8), "#cfd8dc", "SmoothPlastic"))
    parts.append(_part("_root", "Part", "Win", spec.win.pos, spec.win.size, spec.win.color, spec.win.material))

    return {
        "root": "G4Obby",
        "folders": ["Platforms", "Hazards", "Checkpoints", "Moving"],
        "parts": parts,
        "scripts": [{"folder": "_root", "name": "G4Mechanics", "source": get_mechanics_luau()}],
    }
