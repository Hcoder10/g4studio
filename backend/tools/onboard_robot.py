"""Onboard a NEW robot arm from a URDF — automates the manual slog (derive the kinematic chain,
hunt for a working rest-pose branch, report IK coverage). Turns "days per robot" into one command.

    python backend/tools/onboard_robot.py <robot.urdf> [robot_name] [--scale N]

Emits robots/<name>/<name>_chain.lua (drop-in CHAIN + REST for an SO101-style module) and a report.
Mesh baking reuses the existing per-link merge+decimate; the only step that stays manual is the
Roblox mesh UPLOAD (Studio import), which no external tool can do for you.
"""
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from so101_kin import fk_chain, reach_fraction_chain  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _f(s):
    return [float(x) for x in s.split()] if s else [0.0, 0.0, 0.0]


def parse_urdf_chain(path, scale):
    """Return the serial chain of movable (revolute/continuous) joints from base to tip, folding any
    fixed joints into the next movable joint's origin. Each entry: name, pos(studs), rpy, axis, lo, hi."""
    root = ET.parse(path).getroot()
    joints = list(root.findall("joint"))
    by_parent = {}
    for j in joints:
        by_parent.setdefault(j.find("parent").get("link"), []).append(j)
    child_links = {j.find("child").get("link") for j in joints}
    roots = [l.get("name") for l in root.findall("link") if l.get("name") not in child_links]
    link = roots[0]
    chain, pending = [], np.eye(4)

    def origin_mat(j):
        o = j.find("origin")
        xyz = _f(o.get("xyz")) if o is not None else [0, 0, 0]
        rpy = _f(o.get("rpy")) if o is not None else [0, 0, 0]
        from so101_kin import _H, _rpy
        return _H(R=_rpy(*rpy), t=xyz), xyz, rpy

    from so101_kin import _H
    while link in by_parent:
        # follow the actuated branch (prefer revolute/continuous over fixed dead-ends)
        j = sorted(by_parent[link],
                   key=lambda x: 0 if x.get("type") in ("revolute", "continuous") else 1)[0]
        M, xyz, rpy = origin_mat(j)
        jtype = j.get("type")
        if jtype in ("revolute", "continuous"):
            comp = pending @ M              # fold any pending fixed transform into this joint
            t = comp[:3, 3]
            # recover rpy of comp rotation
            R = comp[:3, :3]
            ry = np.arctan2(-R[2, 0], np.hypot(R[0, 0], R[1, 0]))
            rx = np.arctan2(R[2, 1], R[2, 2]); rz = np.arctan2(R[1, 0], R[0, 0])
            ax = _f(j.find("axis").get("xyz")) if j.find("axis") is not None else [0, 0, 1]
            lim = j.find("limit")
            lo, hi = (float(lim.get("lower")), float(lim.get("upper"))) if lim is not None else (-3.14, 3.14)
            chain.append({"name": j.get("name"),
                          "pos": [t[0] * scale, t[1] * scale, t[2] * scale],
                          "rpy": [rx, ry, rz], "axis": ax,
                          "lo": float(np.degrees(lo)), "hi": float(np.degrees(hi))})
            pending = np.eye(4)
        else:                               # fixed: accumulate
            pending = pending @ M
        link = j.find("child").get("link")
    return chain


def auto_rest(chain, base, tries=18, seed=0):
    """Search rest poses for the one with the best forward-workspace reach (selects the IK branch).
    Coarse random search scored by reach fraction — picks the working branch automatically."""
    rng = np.random.default_rng(seed)
    best, best_r = [0.0] * len(chain), -1.0
    cands = [[0.0] * len(chain)]
    for _ in range(tries):
        cands.append([rng.uniform(c["lo"] * 0.6, c["hi"] * 0.6) for c in chain])
    for rest in cands:
        r = reach_fraction_chain(chain, base, rest, n=70)
        if r > best_r:
            best_r, best = r, rest
    return best, best_r


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    urdf = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else \
        os.path.splitext(os.path.basename(urdf))[0]
    scale = 33.0
    if "--scale" in sys.argv:
        scale = float(sys.argv[sys.argv.index("--scale") + 1])

    chain = parse_urdf_chain(urdf, scale)
    base = np.eye(4); base[:3, 3] = [0, 2, 0]
    rest, reach = auto_rest(chain, base)
    F, tip = fk_chain(chain, base, rest)
    span = np.linalg.norm(tip - F[0][:3, 3])

    out = os.path.join(REPO, "robots", name)
    os.makedirs(out, exist_ok=True)
    lua = [f"-- {name}: auto-generated from {os.path.basename(urdf)} by onboard_robot.py",
           f"-- {len(chain)} DOF · workspace reach with auto rest-pose ~ {reach*100:.0f}%", "",
           f"M.SCALE = {scale}", "M.CHAIN = {"]
    for c in chain:
        lua.append("  {{ name = {!r}, pos = Vector3.new({:.4f}, {:.4f}, {:.4f}), "
                   "rpy = {{ {:.6f}, {:.6f}, {:.6f} }}, axis = Vector3.new({:.0f}, {:.0f}, {:.0f}), "
                   "lo = {:.1f}, hi = {:.1f} }},".format(
                       c["name"], *c["pos"], *c["rpy"], *c["axis"], c["lo"], c["hi"]))
    lua.append("}")
    lua.append("M.REST = { " + ", ".join(f"{v:.1f}" for v in rest[:max(4, len(chain) - 1)]) + " }")
    open(os.path.join(out, f"{name}_chain.lua"), "w", encoding="utf-8").write("\n".join(lua))

    print(f"\n  onboarded '{name}' from {os.path.basename(urdf)}")
    print(f"  DOF: {len(chain)}   joints: {[c['name'] for c in chain]}")
    print(f"  auto rest-pose: {[round(v) for v in rest]}   forward-reach: {reach*100:.0f}%   arm span ~{span:.1f} studs")
    print(f"  -> {os.path.join(out, name + '_chain.lua')}")
    print("  next (manual, Roblox-only): bake per-link meshes -> import in Studio -> paste MeshIds.")


if __name__ == "__main__":
    main()
