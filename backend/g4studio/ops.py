"""Canonical build-op vocabulary.

The swarm thinks in high-level *obby primitives* (platforms, hazards, checkpoints,
moving platforms, spinners, decorations, spawn, win). Emitters expand these into
correct Roblox instances plus the templated mechanics scripts. This is the "genre
template" that makes LLM output reliable: the model designs layout/theme, we
guarantee engineering.

Plain dataclasses (no third-party deps) so the offline artifact path always runs.
Coordinates: pos = part CENTER (x, y, z) in studs. Players stand on pos.y + size_y/2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Tuple

Vec3 = Tuple[float, float, float]


def _vec3(v: Any, default: Vec3) -> Vec3:
    if v is None:
        return default
    if isinstance(v, dict):
        return (float(v.get("x", default[0])), float(v.get("y", default[1])), float(v.get("z", default[2])))
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return (float(v[0]), float(v[1]), float(v[2]))
    return default


@dataclass
class Platform:
    pos: Vec3
    size: Vec3 = (8.0, 1.0, 8.0)
    color: str = "#9aa0a6"
    material: str = "SmoothPlastic"
    kind: str = "platform"


@dataclass
class Hazard:
    """Kill brick (lava, spikes, etc.). Touch = death."""
    pos: Vec3
    size: Vec3 = (8.0, 1.0, 8.0)
    color: str = "#ff5a1f"
    material: str = "Neon"
    kind: str = "hazard"


@dataclass
class Checkpoint:
    index: int
    pos: Vec3
    size: Vec3 = (8.0, 1.0, 8.0)
    color: str = "#39d353"
    material: str = "Neon"
    kind: str = "checkpoint"


@dataclass
class Moving:
    """Platform that tweens back and forth along an axis."""
    pos: Vec3
    size: Vec3 = (8.0, 1.0, 8.0)
    axis: str = "x"            # x | z
    distance: float = 16.0     # studs of travel
    speed: float = 8.0         # studs / sec
    color: str = "#4aa3ff"
    material: str = "SmoothPlastic"
    kind: str = "moving"


@dataclass
class Spinner:
    """Rotating kill-bar that sweeps over a platform. Touch = death."""
    pos: Vec3
    size: Vec3 = (16.0, 1.0, 1.0)
    axis: str = "y"            # rotation axis: x | y | z
    speed: float = 90.0        # degrees / sec
    color: str = "#ff2d75"
    material: str = "Neon"
    kind: str = "spinner"


@dataclass
class Decoration:
    """Non-collidable visual flair (pillars, crystals, arches) for theme/richness."""
    pos: Vec3
    size: Vec3 = (2.0, 12.0, 2.0)
    color: str = "#7c4dff"
    material: str = "Neon"
    kind: str = "decoration"


@dataclass
class Spawn:
    pos: Vec3
    kind: str = "spawn"


@dataclass
class Win:
    pos: Vec3
    size: Vec3 = (10.0, 1.0, 10.0)
    color: str = "#ffd400"
    material: str = "Neon"
    kind: str = "win"


@dataclass
class GameSpec:
    name: str = "G4 Obby"
    theme: str = ""
    difficulty: str = "medium"
    spawn: Spawn = field(default_factory=lambda: Spawn(pos=(0.0, 4.0, 0.0)))
    win: Win = field(default_factory=lambda: Win(pos=(0.0, 4.0, 120.0)))
    platforms: List[Platform] = field(default_factory=list)
    hazards: List[Hazard] = field(default_factory=list)
    checkpoints: List[Checkpoint] = field(default_factory=list)
    moving: List[Moving] = field(default_factory=list)
    spinners: List[Spinner] = field(default_factory=list)
    decor: List[Decoration] = field(default_factory=list)

    def part_count(self) -> int:
        return (
            len(self.platforms) + len(self.hazards) + len(self.checkpoints)
            + len(self.moving) + len(self.spinners) + len(self.decor) + 2  # spawn + win
        )


# kind aliases -> canonical bucket
_KIND_MAP = {
    "platform": "platform", "block": "platform", "floor": "platform",
    "hazard": "hazard", "kill": "hazard", "lava": "hazard", "spike": "hazard",
    "checkpoint": "checkpoint", "flag": "checkpoint",
    "moving": "moving", "movingplatform": "moving", "platform_moving": "moving",
    "spinner": "spinner", "spinning": "spinner", "spinbar": "spinner", "blade": "spinner",
    "decoration": "decoration", "decor": "decoration", "prop": "decoration", "pillar": "decoration",
    "spawn": "spawn", "win": "win",
}


def spec_from_dict(d: dict) -> GameSpec:
    """Build a GameSpec from loose LLM JSON. Tolerant of missing fields; accepts
    grouped lists (platforms/hazards/...) and/or a flat `elements` list with `kind`."""
    spec = GameSpec(
        name=str(d.get("name", "G4 Obby")),
        theme=str(d.get("theme", "")),
        difficulty=str(d.get("difficulty", "medium")),
    )

    if isinstance(d.get("spawn"), dict):
        spec.spawn = Spawn(pos=_vec3(d["spawn"].get("pos"), (0.0, 4.0, 0.0)))
    if isinstance(d.get("win"), dict):
        w = d["win"]
        spec.win = Win(pos=_vec3(w.get("pos"), (0.0, 4.0, 120.0)),
                       size=_vec3(w.get("size"), (10.0, 1.0, 10.0)),
                       color=str(w.get("color", "#ffd400")),
                       material=str(w.get("material", "Neon")))

    def add_element(e: dict) -> None:
        kind = _KIND_MAP.get(str(e.get("kind", e.get("type", "platform"))).lower(), "platform")
        if kind == "platform":
            spec.platforms.append(Platform(
                pos=_vec3(e.get("pos"), (0.0, 4.0, 0.0)),
                size=_vec3(e.get("size"), (8.0, 1.0, 8.0)),
                color=str(e.get("color", "#9aa0a6")),
                material=str(e.get("material", "SmoothPlastic"))))
        elif kind == "hazard":
            spec.hazards.append(Hazard(
                pos=_vec3(e.get("pos"), (0.0, 4.0, 0.0)),
                size=_vec3(e.get("size"), (8.0, 1.0, 8.0)),
                color=str(e.get("color", "#ff5a1f")),
                material=str(e.get("material", "Neon"))))
        elif kind == "checkpoint":
            spec.checkpoints.append(Checkpoint(
                index=int(e.get("index", len(spec.checkpoints) + 1)),
                pos=_vec3(e.get("pos"), (0.0, 4.0, 0.0)),
                size=_vec3(e.get("size"), (8.0, 1.0, 8.0)),
                color=str(e.get("color", "#39d353")),
                material=str(e.get("material", "Neon"))))
        elif kind == "moving":
            spec.moving.append(Moving(
                pos=_vec3(e.get("pos"), (0.0, 4.0, 0.0)),
                size=_vec3(e.get("size"), (8.0, 1.0, 8.0)),
                axis=str(e.get("axis", "x")).lower()[:1] or "x",
                distance=float(e.get("distance", 16.0)),
                speed=float(e.get("speed", 8.0)),
                color=str(e.get("color", "#4aa3ff")),
                material=str(e.get("material", "SmoothPlastic"))))
        elif kind == "spinner":
            spec.spinners.append(Spinner(
                pos=_vec3(e.get("pos"), (0.0, 4.0, 0.0)),
                size=_vec3(e.get("size"), (16.0, 1.0, 1.0)),
                axis=str(e.get("axis", "y")).lower()[:1] or "y",
                speed=float(e.get("speed", 90.0)),
                color=str(e.get("color", "#ff2d75")),
                material=str(e.get("material", "Neon"))))
        elif kind == "decoration":
            spec.decor.append(Decoration(
                pos=_vec3(e.get("pos"), (0.0, 4.0, 0.0)),
                size=_vec3(e.get("size"), (2.0, 12.0, 2.0)),
                color=str(e.get("color", "#7c4dff")),
                material=str(e.get("material", "Neon"))))
        elif kind == "spawn":
            spec.spawn = Spawn(pos=_vec3(e.get("pos"), (0.0, 4.0, 0.0)))
        elif kind == "win":
            spec.win = Win(pos=_vec3(e.get("pos"), (0.0, 4.0, 120.0)),
                           size=_vec3(e.get("size"), (10.0, 1.0, 10.0)),
                           color=str(e.get("color", "#ffd400")),
                           material=str(e.get("material", "Neon")))

    for e in d.get("elements", []) or []:
        if isinstance(e, dict):
            add_element(e)
    group_kinds = {
        "platforms": "platform", "hazards": "hazard", "checkpoints": "checkpoint",
        "moving": "moving", "spinners": "spinner", "decor": "decoration",
        "decorations": "decoration",
    }
    for key, kind in group_kinds.items():
        for e in d.get(key, []) or []:
            if isinstance(e, dict):
                e.setdefault("kind", kind)
                add_element(e)

    for i, cp in enumerate(spec.checkpoints, start=1):
        if cp.index <= 0:
            cp.index = i
    return spec
