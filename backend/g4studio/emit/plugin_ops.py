"""Build-ops for the Studio plugin.

Two modes:
  - to_build(spec): the full game as a flat op list (one-shot /api/generate).
  - stage_ops(elements, stage) + to_plugin_event(e): per-stage ops streamed live
    as each builder finishes, so the plugin builds the obby incrementally and shows
    per-agent progress.

Generic ops (folder/part/script) keep the plugin dumb: create instance, set props.
"""
from __future__ import annotations

from typing import Optional

from ..ops import GameSpec
from .common import hex_to_rgb

FOLDERS = ["Platforms", "Hazards", "Checkpoints", "Moving", "Spinners", "Decor"]


def _xyz(v, default) -> list:
    if isinstance(v, dict):
        return [round(float(v.get("x", default[0])), 2),
                round(float(v.get("y", default[1])), 2),
                round(float(v.get("z", default[2])), 2)]
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return [round(float(v[0]), 2), round(float(v[1]), 2), round(float(v[2]), 2)]
    return [float(default[0]), float(default[1]), float(default[2])]


def _op(folder: str, class_name: str, name: str, pos, size, color, material: str, cc: bool = True) -> dict:
    r, g, b = hex_to_rgb(color if isinstance(color, str) else "#9aa0a6")
    return {"folder": folder, "class": class_name, "name": name,
            "pos": _xyz(pos, (0, 4, 0)), "size": _xyz(size, (8, 1, 8)),
            "color": [r, g, b], "material": material, "cc": cc}


# ---- full build (one-shot) -------------------------------------------------
def to_build(spec: GameSpec) -> dict:
    parts = []
    for i, p in enumerate(spec.platforms):
        parts.append(_op("Platforms", "Part", f"Platform{i + 1}", p.pos, p.size, p.color, p.material))
    for i, h in enumerate(spec.hazards):
        parts.append(_op("Hazards", "Part", f"Hazard{i + 1}", h.pos, h.size, h.color, h.material))
    for c in spec.checkpoints:
        parts.append(_op("Checkpoints", "Part", f"Checkpoint{c.index}", c.pos, c.size, c.color, c.material))
    for m in spec.moving:
        parts.append(_op("Moving", "Part", f"Move_{m.axis}_{m.distance}_{m.speed}",
                         m.pos, m.size, m.color, m.material))
    for s in spec.spinners:
        parts.append(_op("Spinners", "Part", f"Spin_{s.axis}_{s.speed}", s.pos, s.size, s.color, s.material))
    for i, d in enumerate(spec.decor):
        parts.append(_op("Decor", "Part", f"Decor{i + 1}", d.pos, d.size, d.color, d.material, cc=False))
    parts.append(_op("_root", "SpawnLocation", "Spawn", spec.spawn.pos, (8, 1, 8), "#cfd8dc", "SmoothPlastic"))
    parts.append(_op("_root", "Part", "Win", spec.win.pos, spec.win.size, spec.win.color, spec.win.material))

    from ..mechanics import get_mechanics_luau
    return {
        "root": "G4Obby",
        "folders": FOLDERS,
        "parts": parts,
        "scripts": [{"folder": "_root", "name": "G4Mechanics", "source": get_mechanics_luau()}],
    }


# ---- per-stage ops (streaming) ---------------------------------------------
def stage_ops(elements: dict, stage: int) -> list:
    """Convert one builder's raw output into part ops for the live plugin build.
    Names are path-ordered by stage index (builders finish out of order)."""
    elements = elements or {}
    ops: list = []
    for i, p in enumerate(elements.get("platforms") or []):
        ops.append(_op("Platforms", "Part", f"S{stage}_P{i + 1}", p.get("pos"), p.get("size"),
                       p.get("color", "#9aa0a6"), p.get("material", "SmoothPlastic")))
    for i, h in enumerate(elements.get("hazards") or []):
        ops.append(_op("Hazards", "Part", f"S{stage}_H{i + 1}", h.get("pos"), h.get("size"),
                       h.get("color", "#ff5a1f"), h.get("material", "Neon")))
    for i, c in enumerate(elements.get("checkpoints") or []):
        ops.append(_op("Checkpoints", "Part", f"Checkpoint{stage + 1}", c.get("pos"), c.get("size"),
                       c.get("color", "#39d353"), c.get("material", "Neon")))
    for m in elements.get("moving") or []:
        axis = str(m.get("axis", "x")).lower()[:1] or "x"
        ops.append(_op("Moving", "Part", f"Move_{axis}_{m.get('distance', 16)}_{m.get('speed', 8)}",
                       m.get("pos"), m.get("size"), m.get("color", "#4aa3ff"),
                       m.get("material", "SmoothPlastic")))
    for s in elements.get("spinners") or []:
        axis = str(s.get("axis", "y")).lower()[:1] or "y"
        ops.append(_op("Spinners", "Part", f"Spin_{axis}_{s.get('speed', 90)}",
                       s.get("pos"), s.get("size") or (16, 1, 1), s.get("color", "#ff2d75"),
                       s.get("material", "Neon")))
    decos = elements.get("decorations") or elements.get("decor") or []
    for i, d in enumerate(decos):
        ops.append(_op("Decor", "Part", f"S{stage}_D{i + 1}", d.get("pos"), d.get("size") or (2, 12, 2),
                       d.get("color", "#7c4dff"), d.get("material", "Neon"), cc=False))
    return ops


def _spawn_win_ops(spawn, win) -> list:
    ops = []
    if spawn:
        ops.append(_op("_root", "SpawnLocation", "Spawn", spawn, (8, 1, 8), "#cfd8dc", "SmoothPlastic"))
    if win:
        ops.append(_op("_root", "Part", "Win", win, (12, 1, 12), "#ffd400", "Neon"))
    return ops


def to_plugin_event(e: dict) -> Optional[dict]:
    """Map a raw swarm event to a plugin-friendly streaming event (or None)."""
    t = e.get("type")
    if t == "director_started":
        return {"type": "agent", "id": "director", "role": "Director", "name": "Director", "status": "working"}
    if t == "director_done":
        return {"type": "agent", "id": "director", "status": "done", "name": e.get("name"),
                "detail": f"{e.get('stages')} stages · {e.get('tps')} tok/s"}
    if t == "builder_started":
        sid = e.get("stage", 0)
        return {"type": "agent", "id": f"b{sid}", "role": "Builder",
                "name": e.get("name") or f"Stage {sid + 1}", "status": "working"}
    if t == "builder_done":
        sid = e.get("stage", 0)
        c = e.get("counts", {}) or {}
        parts = sum(int(v) for v in c.values())
        return {"type": "agent_build", "id": f"b{sid}", "status": "done",
                "detail": f"{parts} parts · {e.get('tps')} tok/s · {e.get('ms')} ms",
                "ops": stage_ops(e.get("elements") or {}, sid)}
    if t == "assembled":
        return {"type": "stage", "ops": _spawn_win_ops(e.get("spawn"), e.get("win"))}
    return None
