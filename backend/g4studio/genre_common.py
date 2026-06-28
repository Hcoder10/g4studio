"""Shared helpers for genre pipelines: build-ops, vectors, config baking."""
from __future__ import annotations

from typing import Any

from .emit.common import hex_to_rgb

VEC3 = {
    "type": "object", "additionalProperties": False,
    "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
    "required": ["x", "y", "z"],
}


def xyz(v: Any, default=(0.0, 4.0, 0.0)) -> list:
    if isinstance(v, dict):
        return [round(float(v.get("x", default[0])), 2),
                round(float(v.get("y", default[1])), 2),
                round(float(v.get("z", default[2])), 2)]
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return [round(float(v[0]), 2), round(float(v[1]), 2), round(float(v[2]), 2)]
    return [float(default[0]), float(default[1]), float(default[2])]


def _rgb(color, default=(154, 160, 166)):
    if isinstance(color, str):
        return list(hex_to_rgb(color))
    if isinstance(color, (list, tuple)) and len(color) == 3:
        return [int(color[0]), int(color[1]), int(color[2])]
    return list(default)


def op(folder: str, name: str, pos, size, color, material: str = "SmoothPlastic",
       cc: bool = True, klass: str = "Part", shape: str = "Block",
       rot: float = 0.0, light=None) -> dict:
    d = {"folder": folder, "class": klass, "name": name,
         "pos": xyz(pos), "size": xyz(size, (4, 1, 4)),
         "color": _rgb(color), "material": material, "cc": cc}
    if shape and shape != "Block":
        d["shape"] = shape
    if rot:
        d["rot"] = round(float(rot), 1)
    if light:
        d["light"] = {"color": _rgb(light.get("color", color)),
                      "brightness": float(light.get("brightness", 2)),
                      "range": float(light.get("range", 16))}
    return d


def emit_ev(cb, type_: str, **data) -> None:
    if cb:
        try:
            cb({"type": type_, **data})
        except Exception:
            pass


def lua_value(v: Any) -> str:
    """Serialize a Python value into a Luau literal (for baked CONFIG tables)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(lua_value(x) for x in v) + "}"
    if isinstance(v, dict):
        parts = []
        for k, val in v.items():
            key = str(k)
            if key.isidentifier():
                parts.append(f"{key} = {lua_value(val)}")
            else:
                parts.append(f'["{key}"] = {lua_value(val)}')
        return "{" + ", ".join(parts) + "}"
    return "nil"
