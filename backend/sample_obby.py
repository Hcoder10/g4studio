"""Offline proof: a hand-authored GameSpec -> real Roblox artifacts. No API key.

Run:  python backend/sample_obby.py
Out:  out/g4obby.rbxmx        (Insert From File into Studio, press Play)
      out/g4obby_build.luau   (paste into command bar as a fallback)

This is the "the game is real" milestone. Once the swarm produces a GameSpec, it
flows through the exact same emitters.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from g4studio.ops import (  # noqa: E402
    GameSpec, Platform, Hazard, Checkpoint, Moving, Spawn, Win,
)
from g4studio.emit import to_rbxmx, to_luau  # noqa: E402


def build_sample() -> GameSpec:
    """A short 'neon lava parkour' obby: ascending platforms, a lava gap,
    two checkpoints, a moving platform, and a win pad."""
    palette = "#1de9b6"
    spec = GameSpec(name="Neon Lava Run", theme="neon lava parkour", difficulty="medium")
    spec.spawn = Spawn(pos=(0.0, 4.0, 0.0))

    z = 0.0
    y = 4.0
    # Stage 1: simple steps
    for i in range(3):
        z += 12
        y += 2
        spec.platforms.append(Platform(pos=(0.0, y, z), size=(8.0, 1.0, 8.0), color=palette))
    spec.checkpoints.append(Checkpoint(index=1, pos=(0.0, y + 1, z)))

    # Lava gap with a kill brick below
    spec.hazards.append(Hazard(pos=(0.0, y - 4, z + 12), size=(10.0, 1.0, 18.0)))
    z += 24
    spec.platforms.append(Platform(pos=(0.0, y, z), size=(8.0, 1.0, 8.0), color=palette))

    # Stage 2: a moving platform crossing
    z += 14
    spec.moving.append(Moving(pos=(0.0, y, z), size=(8.0, 1.0, 8.0),
                              axis="x", distance=18.0, speed=9.0))
    z += 14
    y += 2
    spec.platforms.append(Platform(pos=(0.0, y, z), size=(8.0, 1.0, 8.0), color=palette))
    spec.checkpoints.append(Checkpoint(index=2, pos=(0.0, y + 1, z)))

    # Final stretch to the win pad
    for i in range(2):
        z += 12
        y += 2
        spec.platforms.append(Platform(pos=(0.0, y, z), size=(8.0, 1.0, 8.0), color=palette))
    z += 12
    spec.win = Win(pos=(0.0, y, z), size=(12.0, 1.0, 12.0))
    return spec


def main() -> None:
    spec = build_sample()
    out_dir = os.path.join(os.path.dirname(__file__), "..", "out")
    os.makedirs(out_dir, exist_ok=True)

    rbxmx = to_rbxmx(spec)
    luau = to_luau(spec)

    rbxmx_path = os.path.join(out_dir, "g4obby.rbxmx")
    luau_path = os.path.join(out_dir, "g4obby_build.luau")
    with open(rbxmx_path, "w", encoding="utf-8") as f:
        f.write(rbxmx)
    with open(luau_path, "w", encoding="utf-8") as f:
        f.write(luau)

    print(f"Game: {spec.name}  ({spec.theme}, {spec.difficulty})")
    print(f"  platforms={len(spec.platforms)} hazards={len(spec.hazards)} "
          f"checkpoints={len(spec.checkpoints)} moving={len(spec.moving)} "
          f"parts={spec.part_count()}")
    print(f"  wrote {os.path.abspath(rbxmx_path)}  ({len(rbxmx)} bytes)")
    print(f"  wrote {os.path.abspath(luau_path)}  ({len(luau)} bytes)")
    print("\nIn Studio: right-click Workspace -> Insert From File -> g4obby.rbxmx -> Play")


if __name__ == "__main__":
    main()
