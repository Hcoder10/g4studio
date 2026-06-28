"""Shared helpers for emitters: colors, materials, xml escaping."""
from __future__ import annotations

from typing import Tuple

# Enum.Material -> serialized token value (subset commonly used in obbies).
MATERIAL_TOKENS = {
    "Plastic": 256,
    "SmoothPlastic": 272,
    "Neon": 288,
    "Wood": 512,
    "WoodPlanks": 528,
    "Marble": 784,
    "Slate": 800,
    "Concrete": 816,
    "Granite": 832,
    "Brick": 848,
    "Pebble": 864,
    "Cobblestone": 880,
    "Metal": 1088,
    "DiamondPlate": 1088,
    "Grass": 1280,
    "Sand": 1296,
    "Fabric": 1312,
    "Ice": 1536,
    "Glass": 1568,
    "Foil": 1200,
}


def material_token(name: str) -> int:
    return MATERIAL_TOKENS.get(name, MATERIAL_TOKENS["SmoothPlastic"])


def hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (154, 160, 166)  # neutral grey fallback
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (154, 160, 166)


def color3uint8(h: str) -> int:
    """Pack a hex color into the Color3uint8 serialized integer (0xFF<<24 | rgb)."""
    r, g, b = hex_to_rgb(h)
    return 4278190080 + (r << 16) + (g << 8) + b


def xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
