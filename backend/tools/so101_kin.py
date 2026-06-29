"""SO-101 kinematics in Python (mirrors roblox/robots/SO101.lua): exact URDF FK + damped-least-
squares IK with the down-branch rest pose + joint-limit clamping. Used to (a) auto-find rest poses
when onboarding a robot and (b) synthesize joint-space demonstrations so the LeRobot export + a
behavior-cloning smoke test can run without a human in Studio.
"""
import numpy as np

# exact chain from the URDF (studs), same as SO101.CHAIN. (pos, rpy, lo, hi)
CHAIN = [
    ((1.2816, -0.0, 2.0592), (3.14159, 0, -3.14159), -110, 110),
    ((-1.0032, -0.6032, -1.7886), (-1.5708, -1.5708, 0), -100, 100),
    ((-3.7148, -0.9240, 0.0), (0, 0, 1.5708), -96.8, 96.8),
    ((-4.4517, 0.1716, 0.0), (0, 0, -1.5708), -95, 95),
    ((0.0, -2.0163, 0.5973), (1.5708, 0.04868, 3.14159), -157.2, 162.8),
    ((0.6666, 0.6204, -0.7722), (1.5708, 0, 0), -10, 100),
]
STATE_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
REST = [0.0, 20.0, 85.0, -55.0, 0.0]   # down-reaching branch
GRIP_CLOSED, GRIP_OPEN = 0.0, 55.0


def _Rx(a): c, s = np.cos(a), np.sin(a); return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
def _Ry(a): c, s = np.cos(a), np.sin(a); return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
def _Rz(a): c, s = np.cos(a), np.sin(a); return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
def _H(R=np.eye(3), t=(0, 0, 0)): M = np.eye(4); M[:3, :3] = R; M[:3, 3] = t; return M
def _cfa(x, y, z): return _H(R=_Rx(x) @ _Ry(y) @ _Rz(z))
def _aa(th): c, s = np.cos(th), np.sin(th); return _H(R=np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]))
def _rpy(r, p, y): return _Rz(y) @ _Ry(p) @ _Rx(r)


UPFIX = _cfa(-np.pi / 2, 0, 0)
TIP = _H(t=(-0.2607, -0.0072, -3.2380)) @ _cfa(0, np.pi, 0)


def fk(base, ang):
    """ang = [j1..j5(, j6)] degrees. Returns (link frames 1..6, tip xyz)."""
    cf = base @ UPFIX
    F = []
    a = list(ang) + [0.0] * (6 - len(ang))
    for i, (pos, r, lo, hi) in enumerate(CHAIN):
        cf = cf @ _H(R=_rpy(*r), t=pos) @ _aa(np.radians(a[i]))
        F.append(cf)
    return F, (F[4] @ TIP)[:3, 3]


def solve_to(base, targets, world_target, rest=REST, posture=0.12, lam2=0.6, iters=8):
    """DLS IK with null-space posture + joint-limit clamping. targets = current joint TARGETS (deg,
    j1..j4); returns updated j1..j4 deg. Reach-clamped to the shoulder shell."""
    F, _ = fk(base, list(targets) + [0, GRIP_OPEN]); sh = F[1][:3, 3]
    d0 = world_target - sh; dist = np.linalg.norm(d0)
    if dist > 8.4: world_target = sh + d0 * (8.4 / dist)
    elif 1e-3 < dist < 2.6: world_target = sh + d0 * (2.6 / dist)
    q = [np.radians(targets[i]) for i in range(4)]
    lim = [(np.radians(CHAIN[c][2]), np.radians(CHAIN[c][3])) for c in range(4)]
    for _ in range(iters):
        ang = [np.degrees(q[i]) for i in range(4)] + [0, GRIP_OPEN]
        F, tip = fk(base, ang); e = world_target - tip
        if np.linalg.norm(e) < 0.08: break
        if np.linalg.norm(e) > 2: e *= 2 / np.linalg.norm(e)
        Jc = [np.cross(F[c][:3, :3] @ np.array([0, 0, 1.]), tip - F[c][:3, 3]) for c in range(4)]

        def step(cols):
            M = lam2 * np.eye(3)
            for c in cols: M += np.outer(Jc[c], Jc[c])
            Mi = np.linalg.inv(M); y = Mi @ e; dq = [0, 0, 0, 0]
            for c in cols: dq[c] = float(np.dot(Jc[c], y))
            z = [np.radians(rest[c]) - q[c] for c in range(4)]; zc = sum(Jc[c] * z[c] for c in cols)
            for c in cols: dq[c] += posture * (z[c] - np.dot(Mi @ Jc[c], zc))
            return dq
        dq = step([0, 1, 2, 3])
        bad = [c for c in range(4) if not (lim[c][0] <= q[c] + dq[c] <= lim[c][1])]
        if bad:
            cols = [c for c in range(4) if c not in bad]
            dq = step(cols) if cols else [0, 0, 0, 0]
        for c in range(4): q[c] = np.clip(q[c] + dq[c], lim[c][0], lim[c][1])
    return [np.degrees(q[i]) for i in range(4)]


# ---------------------------------------------------------------------------
# GENERAL chain kinematics (any URDF arm) — used by onboard_robot.py
# ---------------------------------------------------------------------------
def _aa_axis(axis, th):
    ax = np.array(axis, float); ax = ax / (np.linalg.norm(ax) + 1e-12)
    x, y, z = ax; c, s = np.cos(th), np.sin(th); C = 1 - c
    return _H(R=np.array([
        [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C]]))


def fk_chain(chain, base, angles):
    """chain = [{pos(studs), rpy, axis, lo, hi}, ...]; tip = last link frame origin."""
    cf = base @ UPFIX
    F = []
    for i, j in enumerate(chain):
        cf = cf @ _H(R=_rpy(*j["rpy"]), t=j["pos"]) @ _aa_axis(j["axis"], np.radians(angles[i]))
        F.append(cf)
    return F, F[-1][:3, 3]


def solve_chain(chain, base, targets, world_target, rest, posture=0.1, lam2=0.6, iters=10):
    """Damped-least-squares IK over an arbitrary revolute chain, with null-space posture toward
    `rest` and joint-limit clamping. Returns updated joint targets (deg)."""
    n = len(chain)
    q = [np.radians(targets[i]) for i in range(n)]
    lim = [(np.radians(c["lo"]), np.radians(c["hi"])) for c in chain]
    for _ in range(iters):
        F, tip = fk_chain(chain, base, [np.degrees(v) for v in q])
        e = world_target - tip
        if np.linalg.norm(e) < 0.08: break
        if np.linalg.norm(e) > 2: e *= 2 / np.linalg.norm(e)
        Jc = [np.cross(F[c][:3, :3] @ np.array(chain[c]["axis"], float), tip - F[c][:3, 3]) for c in range(n)]

        def step(cols):
            M = lam2 * np.eye(3)
            for c in cols: M += np.outer(Jc[c], Jc[c])
            Mi = np.linalg.inv(M); y = Mi @ e; dq = [0.0] * n
            for c in cols: dq[c] = float(np.dot(Jc[c], y))
            z = [np.radians(rest[c]) - q[c] for c in range(n)]; zc = sum(Jc[c] * z[c] for c in cols)
            for c in cols: dq[c] += posture * (z[c] - np.dot(Mi @ Jc[c], zc))
            return dq
        dq = step(list(range(n)))
        bad = [c for c in range(n) if not (lim[c][0] <= q[c] + dq[c] <= lim[c][1])]
        if bad:
            cols = [c for c in range(n) if c not in bad]
            dq = step(cols) if cols else [0.0] * n
        for c in range(n): q[c] = float(np.clip(q[c] + dq[c], lim[c][0], lim[c][1]))
    return [np.degrees(q[i]) for i in range(n)]


def reach_fraction_chain(chain, base, rest, n=300, seed=0):
    """Fraction of a forward workspace box this rest pose can reach — the score for rest-pose search."""
    rng = np.random.default_rng(seed)
    F0, tip0 = fk_chain(chain, base, rest)
    sh = F0[min(1, len(chain) - 1)][:3, 3]
    span = max(2.0, np.linalg.norm(tip0 - sh))   # rough arm scale
    ok = tot = 0
    for _ in range(n):
        T = sh + np.array([rng.uniform(-span, span), rng.uniform(-span, 0.2 * span),
                           rng.uniform(0.3 * span, 1.2 * span)])
        tot += 1
        t = list(rest)
        for _ in range(18): t = solve_chain(chain, base, t, T, rest)
        _, tip = fk_chain(chain, base, t)
        ok += np.linalg.norm(T - tip) < 0.08 * span + 0.3
    return ok / tot


def reach_fraction(base, rest, n=600, seed=0):
    """How much of the forward table workspace this rest pose can reach (for auto rest-pose search)."""
    rng = np.random.default_rng(seed); F0, _ = fk(base, rest + [0, GRIP_OPEN]); sh = F0[1][:3, 3]
    ok = tot = 0
    for _ in range(n):
        T = sh + np.array([rng.uniform(-5, 5), rng.uniform(-5, -1), rng.uniform(2, 6)])
        tot += 1
        t = list(rest[:4])
        for _ in range(20): t = solve_to(base, t, T, rest=rest)
        _, tip = fk(base, t + [0, GRIP_OPEN])
        ok += np.linalg.norm(T - tip) < 0.4
    return ok / tot
