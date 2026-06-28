"""Prebuilt asset kit — composite props made of real shaped parts (not generated
from scratch each time). Builders place assets BY NAME; expand() turns a placement
into the asset's parts at an anchor, with per-instance variation (scale / rotation /
color jitter) so a forest of trees doesn't look copy-pasted, plus real PointLights
on glowing props.

Each asset is a list of sub-parts with offsets (relative to the anchor on the floor).
Shapes: Block (default), Ball, Cylinder via Part.Shape; Wedge via class WedgePart.
"""
from __future__ import annotations

import math
import random

from .emit.common import hex_to_rgb
from .genre_common import op as _mkop


def _s(off, size, color, material="SmoothPlastic", shape="Block", cc=True, klass="Part", light=None):
    return {"off": off, "size": size, "color": color, "material": material,
            "shape": shape, "cc": cc, "class": klass, "light": light}


# light presets
_FIRE = {"color": "#ff8a2a", "brightness": 2.6, "range": 18}
_LAMP = {"color": "#fff1a8", "brightness": 2.2, "range": 22}
_GLOW = {"color": "#8be9ff", "brightness": 1.6, "range": 12}

# anchor = point on the floor; +Y offsets stack the prop upward.
ASSETS = {
    # ---- decorative props (multi-part) ----
    "tree": lambda p: [
        _s([0, 3, 0], [1.4, 6, 1.4], "#6b4a2a", "Wood", "Cylinder"),
        _s([0, 7.5, 0], [7, 6, 7], "#2e8b57", "Grass", "Ball", cc=False)],
    "pine": lambda p: [
        _s([0, 2.5, 0], [1.2, 5, 1.2], "#5b3a1a", "Wood", "Cylinder"),
        _s([0, 6, 0], [5, 5, 5], "#1f6f3f", "Grass", "Ball", cc=False),
        _s([0, 9, 0], [3, 4, 3], "#258050", "Grass", "Ball", cc=False)],
    "rock": lambda p: [_s([0, 1.4, 0], [4.5, 3.2, 4.5], "#8a8f98", "Slate", "Ball")],
    "boulder": lambda p: [
        _s([0, 2, 0], [7, 5, 7], "#7c828c", "Slate", "Ball"),
        _s([3, 1, 2], [3, 2.5, 3], "#8a8f98", "Slate", "Ball")],
    "bush": lambda p: [_s([0, 1.2, 0], [4, 2.6, 4], "#3aa55a", "Grass", "Ball", cc=False)],
    "crate": lambda p: [_s([0, 1.5, 0], [3, 3, 3], "#9c6b3f", "WoodPlanks", "Block")],
    "barrel": lambda p: [_s([0, 1.8, 0], [2.4, 3.6, 2.4], "#7a4a28", "Wood", "Cylinder")],
    "pillar": lambda p: [
        _s([0, 6, 0], [2.4, 12, 2.4], "#cdd2da", "Marble", "Cylinder"),
        _s([0, 12.2, 0], [3.2, 0.6, 3.2], "#e8ecf2", "Marble", "Block"),
        _s([0, 0.3, 0], [3.2, 0.6, 3.2], "#e8ecf2", "Marble", "Block")],
    "arch": lambda p: [
        _s([-4, 5, 0], [1.6, 10, 1.6], "#cdd2da", "Marble", "Cylinder"),
        _s([4, 5, 0], [1.6, 10, 1.6], "#cdd2da", "Marble", "Cylinder"),
        _s([0, 10.5, 0], [10, 1.6, 1.6], "#e8ecf2", "Marble", "Block")],
    "torch": lambda p: [
        _s([0, 2.5, 0], [0.5, 5, 0.5], "#3a2a1a", "Wood", "Cylinder"),
        _s([0, 5.4, 0], [1.1, 1.4, 1.1], "#ff7a1a", "Neon", "Ball", cc=False, light=_FIRE)],
    "lamp": lambda p: [
        _s([0, 4, 0], [0.6, 8, 0.6], "#2b2f36", "Metal", "Cylinder"),
        _s([0, 8.3, 0], [1.6, 1.6, 1.6], "#fff1a8", "Neon", "Ball", cc=False, light=_LAMP)],
    "crystal": lambda p: [
        _s([0, 2.4, 0], [2, 5, 2], (p[1] if len(p) > 1 else "#7c4dff"), "Glass", "Cylinder",
           cc=False, light=_GLOW),
        _s([1.4, 1.4, 0.6], [1.2, 3, 1.2], (p[0] if p else "#4aa3ff"), "Glass", "Cylinder", cc=False)],
    "fence": lambda p: [
        _s([0, 1.5, 0], [8, 0.6, 0.4], "#6b4a2a", "Wood", "Block"),
        _s([-3.5, 1, 0], [0.6, 3, 0.6], "#5b3a1a", "Wood", "Block"),
        _s([3.5, 1, 0], [0.6, 3, 0.6], "#5b3a1a", "Wood", "Block")],
    "tent": lambda p: [
        _s([0, 2, 0], [6, 4, 6], (p[0] if p else "#c0563a"), "Fabric", "Wedge", klass="WedgePart")],
    # ---- structure ----
    "platform": lambda p: [_s([0, 0.5, 0], [10, 1, 10], (p[0] if p else "#9aa0a6"), "SmoothPlastic", "Block")],
    "wall": lambda p: [_s([0, 5, 0], [12, 10, 1.5], (p[0] if p else "#7c828c"), "Concrete", "Block")],
    "ramp": lambda p: [_s([0, 2, 0], [6, 4, 10], (p[0] if p else "#9aa0a6"), "SmoothPlastic", "Wedge", klass="WedgePart")],
    # ---- gameplay objects (single part so a folder child IS the interactive part) ----
    "coin": lambda p: [_s([0, 2, 0], [3, 0.5, 3], "#ffd400", "Neon", "Cylinder", cc=False,
                          light={"color": "#ffd400", "brightness": 1.1, "range": 7})],
    "gem": lambda p: [_s([0, 2, 0], [2.2, 2.6, 2.2], "#00e5ff", "Neon", "Ball", cc=False, light=_GLOW)],
    "orb": lambda p: [_s([0, 2, 0], [2, 2, 2], (p[0] if p else "#1de9b6"), "Neon", "Ball", cc=False,
                         light={"color": "#1de9b6", "brightness": 1.2, "range": 8})],
    "button": lambda p: [_s([0, 0.5, 0], [5, 1, 5], "#ff4d4d", "Neon", "Cylinder")],
    "flag": lambda p: [_s([0, 3, 0], [4, 6, 4], "#ffd400", "Neon", "Ball", cc=False,
                          light={"color": "#ffd400", "brightness": 2, "range": 16})],
    "coin_pile": lambda p: [_s([0, 1.2, 0], [4, 2.4, 4], "#ffd400", "Neon", "Ball", cc=False,
                               light={"color": "#ffd400", "brightness": 1.4, "range": 10})],
}

ASSET_NAMES = list(ASSETS.keys())
GAMEPLAY_ASSETS = ["coin", "gem", "orb", "button", "flag", "coin_pile"]


def _jitter(rgb, amt=0.10):
    out = []
    for c in rgb:
        out.append(max(0, min(255, int(c * (1.0 + random.uniform(-amt, amt))))))
    return out


def expand(asset: str, folder: str, name: str, anchor, palette, vary: bool = True) -> list:
    """A placement -> the asset's part ops at the anchor, with per-instance variation."""
    subs = ASSETS.get(asset, ASSETS["crate"])(palette or [])
    ang = random.uniform(0, 360) if vary else 0.0
    scale = random.uniform(0.85, 1.18) if vary else 1.0
    rad = math.radians(ang)
    ca, sa = math.cos(rad), math.sin(rad)
    multi = len(subs) > 1
    ops = []
    for i, s in enumerate(subs):
        dx, dy, dz = s["off"]
        rx = (dx * ca - dz * sa) * scale
        rz = (dx * sa + dz * ca) * scale
        pos = [anchor[0] + rx, anchor[1] + dy * scale, anchor[2] + rz]
        size = [s["size"][0] * scale, s["size"][1] * scale, s["size"][2] * scale]
        color = _jitter(hex_to_rgb(s["color"])) if isinstance(s["color"], str) and vary else s["color"]
        nm = f"{name}_{i}" if multi else name
        ops.append(_mkop(folder, nm, pos, size, color, s["material"], s.get("cc", True),
                         s.get("class", "Part"), s.get("shape", "Block"), rot=ang, light=s.get("light")))
    return ops
