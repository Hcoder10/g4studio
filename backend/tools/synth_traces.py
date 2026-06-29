"""Synthesize joint-space pick-and-place demonstrations by driving the actual SO-101 kinematics
with a scripted policy. Writes episodes in the SAME schema the in-Studio Trace recorder uses, so the
LeRobot export + behavior-cloning smoke test run end-to-end without a human in Studio. (It also
doubles as a headless playtester for the data pipeline.)

    python backend/tools/synth_traces.py [n_episodes]   ->   datasets/so101_synth_pickplace.jsonl
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from so101_kin import CHAIN, GRIP_OPEN, REST, STATE_NAMES, _H, fk, solve_to  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = _H(t=(0, 2, 0))
FPS = 30
SPEED = 200.0      # deg/s servo cap (matches SO101.SPEED_DEG)


def _episode(cube, bin_pos, rng):
    angles = list(REST) + [0.0]      # [j1..j5, gripper-as-deg-placeholder]; index 5 unused for tip
    grip = 1.0                       # 0 closed .. 1 open
    targets = list(REST[:4])
    held = False
    cube = np.array(cube, float)
    dt = 1.0 / FPS
    plan = [
        (cube + [0, 2.6, 0], 1.0, "reach"),
        (cube + [0, 0.3, 0], 1.0, "reach"),
        (cube + [0, 0.3, 0], 0.0, "grasp"),       # close
        (cube + [0, 2.6, 0], 0.0, "transport"),
        (np.array(bin_pos) + [0, 3.0, 0], 0.0, "transport"),
        (np.array(bin_pos) + [0, 1.3, 0], 0.0, "place"),
        (np.array(bin_pos) + [0, 1.3, 0], 1.0, "place"),  # release
    ]
    steps = []
    for (wp, gtarget, subgoal) in plan:
        for _ in range(int(0.9 * FPS)):
            targets = solve_to(BASE, targets, np.array(wp, float))
            for c in range(4):
                err = targets[c] - angles[c]
                angles[c] += float(np.clip(err, -SPEED * dt, SPEED * dt))
            grip += float(np.clip(gtarget - grip, -3 * dt, 3 * dt))
            _, tip = fk(BASE, angles[:5])
            if grip < 0.35 and not held and np.linalg.norm(cube - tip) < 1.8:
                held = True
            elif grip > 0.6 and held:
                held = False
            if held:
                cube = tip.copy()
            state = [angles[0], angles[1], angles[2], angles[3], angles[4], grip]
            action = [targets[0], targets[1], targets[2], targets[3], 0.0, gtarget]
            reward = -0.02 * float(np.linalg.norm(tip - np.array(wp, float)))
            steps.append({"obs": {"state": state, "ee": tip.tolist(), "holding": held},
                          "action": action, "reward": reward, "subgoal": subgoal})
    success = bool(np.linalg.norm(cube - np.array(bin_pos, float)) < 2.0)
    if success and steps:
        steps[-1]["reward"] += 5.0
    return steps, success


def main(n=120):
    rng = np.random.default_rng(0)
    F0, _ = fk(BASE, REST + [0]); sh = F0[1][:3, 3]
    out = os.path.join(REPO, "datasets", "so101_synth_pickplace.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    meta = {"robot": "SO101", "game": "synthetic pick-place", "fps": FPS,
            "action_space": "joint_position", "state_names": STATE_NAMES, "action_names": STATE_NAMES}
    n_ok = 0
    with open(out, "w", encoding="utf-8") as f:
        for _ in range(n):
            cube = sh + np.array([rng.uniform(-3, 3), rng.uniform(-5, -4), rng.uniform(3, 5)])
            binp = sh + np.array([rng.uniform(-2, 2), -4.7, rng.uniform(3, 4.5)])
            steps, ok = _episode(cube, binp, rng)
            n_ok += ok
            f.write(json.dumps({"task": "so101_synth_pickplace", "meta": meta,
                                "success": ok, "score": 1 if ok else 0,
                                "length": len(steps), "steps": steps}) + "\n")
    print(f"wrote {out}: {n} episodes, {n_ok} successful ({100*n_ok//n}%), "
          f"~{sum(len(_episode(sh+[0,-4.5,4], sh+[0,-4.7,3.5], rng)[0]) for _ in range(1))} frames/ep")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 120)
