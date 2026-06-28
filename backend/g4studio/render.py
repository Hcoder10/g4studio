"""Render a build dict to an image the vision playtester can see — no Roblox needed.

Two orthographic panels:
  LEFT  = top-down map  (X right, Z up)
  RIGHT = side elevation (Z right, Y up = height)  -> shows gaps + jump heights
Pillow only. Returns PNG bytes / a base64 data URI for Gemma-4 vision.
"""
from __future__ import annotations

import base64
import io
from typing import Optional

from PIL import Image, ImageDraw

BG = (10, 14, 20)
GRID = (28, 38, 52)
TEXT = (200, 215, 230)


def _bounds(parts):
    xs0, xs1, ys0, ys1, zs0, zs1 = [], [], [], [], [], []
    for p in parts:
        px, py, pz = p["pos"]
        sx, sy, sz = p["size"]
        xs0.append(px - sx / 2); xs1.append(px + sx / 2)
        ys0.append(py - sy / 2); ys1.append(py + sy / 2)
        zs0.append(pz - sz / 2); zs1.append(pz + sz / 2)
    return (min(xs0), max(xs1), min(ys0), max(ys1), min(zs0), max(zs1))


def render_build(build: dict, panel: int = 440, pad: int = 34) -> bytes:
    parts = [p for p in build.get("parts", []) if "pos" in p and "size" in p]
    W = panel * 2 + pad * 3
    H = panel + pad * 2 + 22
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")
    if not parts:
        d.text((pad, pad), "empty build", fill=TEXT)
        buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()

    minx, maxx, miny, maxy, minz, maxz = _bounds(parts)
    ex, ey, ez = max(maxx - minx, 1), max(maxy - miny, 1), max(maxz - minz, 1)

    # panel rects
    lx, rx, ty = pad, pad * 2 + panel, pad + 18
    d.text((lx, pad - 2), "TOP-DOWN  (X right, Z up)", fill=TEXT)
    d.text((rx, pad - 2), "SIDE  (Z right, height up)", fill=TEXT)
    for ox in (lx, rx):
        d.rectangle([ox, ty, ox + panel, ty + panel], outline=GRID, width=1)

    def fit(extent):
        return (panel - 2 * pad) / extent

    s_top = min(fit(ex), fit(ez))
    s_side = min(fit(ez), fit(ey))

    def col(p, a=235):
        c = p.get("color", [150, 150, 150])
        return (int(c[0]), int(c[1]), int(c[2]), a)

    # TOP-DOWN: x->u, z->v (invert v so +Z is up). Draw lower parts first.
    for p in sorted(parts, key=lambda q: q["pos"][1]):
        px, _, pz = p["pos"]; sx, _, sz = p["size"]
        u0 = lx + pad + (px - sx / 2 - minx) * s_top
        u1 = lx + pad + (px + sx / 2 - minx) * s_top
        v1 = ty + panel - pad - (pz - sz / 2 - minz) * s_top
        v0 = ty + panel - pad - (pz + sz / 2 - minz) * s_top
        a = 150 if not p.get("cc", True) else 235
        d.rectangle([u0, v0, u1, v1], fill=col(p, a), outline=(0, 0, 0, 120))

    # SIDE: z->u, y->v (invert v so +Y is up).
    for p in sorted(parts, key=lambda q: q["pos"][0]):
        _, py, pz = p["pos"]; _, sy, sz = p["size"]
        u0 = rx + pad + (pz - sz / 2 - minz) * s_side
        u1 = rx + pad + (pz + sz / 2 - minz) * s_side
        v1 = ty + panel - pad - (py - sy / 2 - miny) * s_side
        v0 = ty + panel - pad - (py + sy / 2 - miny) * s_side
        a = 150 if not p.get("cc", True) else 235
        d.rectangle([u0, v0, u1, v1], fill=col(p, a), outline=(0, 0, 0, 120))

    # mark spawn / goal on the top-down
    def mark(name, color, label):
        for p in parts:
            if p.get("name") == name or p.get("folder") == name:
                px, _, pz = p["pos"]
                u = lx + pad + (px - minx) * s_top
                v = ty + panel - pad - (pz - minz) * s_top
                d.ellipse([u - 6, v - 6, u + 6, v + 6], fill=color, outline=(255, 255, 255, 255))
                d.text((u + 8, v - 6), label, fill=color)
                return
    mark("Spawn", (57, 211, 83, 255), "spawn")
    mark("Win", (255, 212, 0, 255), "goal")
    mark("Goal", (255, 212, 0, 255), "goal")

    buf = io.BytesIO(); img.save(buf, format="PNG")
    return buf.getvalue()


def render_data_uri(build: dict) -> str:
    png = render_build(build)
    return "data:image/png;base64," + base64.b64encode(png).decode()
