"""Deterministic Roblox-API validator — catches the model's main weakness
(hallucinated Enums) so the harness can feed PRECISE errors back for repair,
without ever taking authoring control away from the model.

We only validate small, well-defined enums where a complete whitelist is safe
(false positives would be worse than misses). Material + PartType cover the
common error sites (e.g. the model loves to invent `Enum.Material.Rock`).
"""
from __future__ import annotations

import re

# Complete, current Enum.Material member set.
MATERIALS = {
    "Plastic", "SmoothPlastic", "Neon", "Wood", "WoodPlanks", "Marble", "Basalt",
    "Slate", "CrackedLava", "Concrete", "Limestone", "Granite", "Pavement", "Brick",
    "Pebble", "Cobblestone", "Mud", "Sandstone", "Sand", "Fabric", "Grass",
    "LeafyGrass", "Ground", "Ice", "Glacier", "Snow", "Salt", "Asphalt", "Metal",
    "CorrodedMetal", "DiamondPlate", "Foil", "Glass", "ForceField", "Air", "Water",
}
PART_TYPES = {"Ball", "Block", "Cylinder", "Wedge", "CornerWedge"}
EASING_STYLES = {"Linear", "Sine", "Back", "Quad", "Quart", "Quint", "Bounce",
                 "Elastic", "Exponential", "Circular", "Cubic"}
EASING_DIRS = {"In", "Out", "InOut"}

# common hallucination -> suggestion
_SUGGEST = {
    "Rock": "Slate, Basalt, Cobblestone or Concrete",
    "Stone": "Slate, Basalt or Concrete",
    "Dirt": "Ground or Mud",
    "Lava": "CrackedLava or Neon",
    "Gold": "Metal or Foil (use Color for the gold look)",
    "Crystal": "Glass or Neon",
    "Leaves": "Grass or LeafyGrass",
}


def find_api_issues(src: str) -> list[str]:
    issues = []
    for m in re.finditer(r"Enum\.Material\.(\w+)", src):
        name = m.group(1)
        if name not in MATERIALS:
            hint = f" (use {_SUGGEST[name]})" if name in _SUGGEST else " (not a real Material)"
            issues.append(f"Enum.Material.{name} is INVALID{hint}")
    for m in re.finditer(r"Enum\.PartType\.(\w+)", src):
        name = m.group(1)
        if name not in PART_TYPES:
            issues.append(f"Enum.PartType.{name} is INVALID (only Ball/Block/Cylinder/Wedge/CornerWedge)")
    for m in re.finditer(r"Enum\.EasingStyle\.(\w+)", src):
        if m.group(1) not in EASING_STYLES:
            issues.append(f"Enum.EasingStyle.{m.group(1)} is INVALID")
    for m in re.finditer(r"Enum\.EasingDirection\.(\w+)", src):
        if m.group(1) not in EASING_DIRS:
            issues.append(f"Enum.EasingDirection.{m.group(1)} is INVALID (only In/Out/InOut)")
    return sorted(set(issues))
