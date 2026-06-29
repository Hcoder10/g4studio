"""Export collected manipulation traces (datasets/<task>.jsonl) to the LeRobot v2.1 dataset format:
meta/{info.json,episodes.jsonl,tasks.jsonl,stats.json} + data/chunk-000/episode_*.parquet, one row
per timestep with observation.state (joint angles) and action (commanded joint targets).

    python backend/tools/lerobot_export.py [task]   ->   lerobot_datasets/<task>/
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "datasets")
OUT = os.path.join(REPO, "lerobot_datasets")


def export(task=None):
    results = {}
    for f in sorted(glob.glob(os.path.join(SRC, "*.jsonl"))):
        tname = os.path.basename(f)[:-6]
        if task and tname != task:
            continue
        eps = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        eps = [e for e in eps if e.get("steps")]
        if not eps:
            continue
        out = os.path.join(OUT, tname)
        os.makedirs(os.path.join(out, "meta"), exist_ok=True)
        os.makedirs(os.path.join(out, "data", "chunk-000"), exist_ok=True)
        m0 = eps[0].get("meta", {})
        names = m0.get("state_names") or [f"j{i}" for i in range(len(eps[0]["steps"][0]["obs"]["state"]))]
        fps = int(m0.get("fps", 30))
        sdim = len(eps[0]["steps"][0]["obs"]["state"])
        adim = len(eps[0]["steps"][0]["action"])

        all_states, all_actions, all_rewards = [], [], []
        ep_meta, gidx = [], 0
        for ei, ep in enumerate(eps):
            steps = ep["steps"]
            recs = []
            for fi, st in enumerate(steps):
                s = [float(x) for x in st["obs"]["state"]]
                a = [float(x) for x in st["action"]]
                all_states.append(s); all_actions.append(a); all_rewards.append(float(st.get("reward", 0)))
                recs.append({
                    "observation.state": s, "action": a,
                    "timestamp": fi / fps, "frame_index": fi, "episode_index": ei, "index": gidx,
                    "task_index": 0, "next.reward": float(st.get("reward", 0)),
                    "next.done": fi == len(steps) - 1,
                    "next.success": bool(ep.get("success")) and fi == len(steps) - 1,
                    "subgoal": st.get("subgoal") or "",
                })
                gidx += 1
            pd.DataFrame(recs).to_parquet(os.path.join(out, "data", "chunk-000", f"episode_{ei:06d}.parquet"))
            ep_meta.append({"episode_index": ei, "tasks": [m0.get("game", tname)], "length": len(steps)})

        S, A = np.array(all_states, np.float32), np.array(all_actions, np.float32)

        def stat(x):
            return {"mean": x.mean(0).tolist(), "std": (x.std(0) + 1e-8).tolist(),
                    "min": x.min(0).tolist(), "max": x.max(0).tolist()}
        info = {
            "codebase_version": "v2.1", "robot_type": m0.get("robot", "SO101"), "fps": fps,
            "total_episodes": len(eps), "total_frames": gidx, "total_tasks": 1, "total_chunks": 1,
            "chunks_size": 1000,
            "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
            "features": {
                "observation.state": {"dtype": "float32", "shape": [sdim], "names": names},
                "action": {"dtype": "float32", "shape": [adim], "names": names},
                "next.reward": {"dtype": "float32", "shape": [1]},
                "next.done": {"dtype": "bool", "shape": [1]},
            },
        }
        json.dump(info, open(os.path.join(out, "meta", "info.json"), "w"), indent=2)
        with open(os.path.join(out, "meta", "episodes.jsonl"), "w") as fo:
            for e in ep_meta:
                fo.write(json.dumps(e) + "\n")
        with open(os.path.join(out, "meta", "tasks.jsonl"), "w") as fo:
            fo.write(json.dumps({"task_index": 0, "task": m0.get("game", tname)}) + "\n")
        json.dump({"observation.state": stat(S), "action": stat(A),
                   "next.reward": stat(np.array(all_rewards, np.float32).reshape(-1, 1))},
                  open(os.path.join(out, "meta", "stats.json"), "w"), indent=2)
        results[tname] = {"episodes": len(eps), "frames": gidx, "out": out}
    return results


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else None
    res = export(task)
    if not res:
        print("no datasets found in", SRC)
    for t, r in res.items():
        print(f"{t}: {r['episodes']} episodes, {r['frames']} frames -> {r['out']} (LeRobot v2.1)")
