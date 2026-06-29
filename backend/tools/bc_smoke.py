"""Behavior-cloning smoke test: train a small MLP to predict the next joint action from the joint
state on the collected (or synthesized) traces, and compare to a predict-the-mean baseline. If the
BC error is well below baseline, the data carries a learnable manipulation policy — i.e. it's real
training data, not just well-shaped noise. (Sim data; this validates learnability, not sim-to-real.)

    python backend/tools/bc_smoke.py [task]
"""
import glob
import json
import os
import sys

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPRegressor

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(task=None):
    X, Y = [], []
    for f in sorted(glob.glob(os.path.join(REPO, "datasets", "*.jsonl"))):
        if task and os.path.basename(f)[:-6] != task:
            continue
        for line in open(f, encoding="utf-8"):
            if not line.strip():
                continue
            ep = json.loads(line)
            for st in ep.get("steps", []):
                X.append(st["obs"]["state"]); Y.append(st["action"])
    return np.array(X, np.float32), np.array(Y, np.float32)


def main(task=None):
    X, Y = load(task)
    if len(X) < 200:
        print(f"only {len(X)} frames — collect/synthesize more first."); return
    # normalize
    xm, xs = X.mean(0), X.std(0) + 1e-6
    ym, ys = Y.mean(0), Y.std(0) + 1e-6
    Xn, Yn = (X - xm) / xs, (Y - ym) / ys
    Xtr, Xte, Ytr, Yte = train_test_split(Xn, Yn, test_size=0.2, random_state=0)
    mlp = MLPRegressor(hidden_layer_sizes=(128, 128), max_iter=400, random_state=0).fit(Xtr, Ytr)
    pred = mlp.predict(Xte)
    bc_mse = float(((pred - Yte) ** 2).mean())
    base_mse = float(((Ytr.mean(0) - Yte) ** 2).mean())          # predict-the-mean
    # per-joint R^2 in original units
    pred_real = pred * ys + ym
    Yte_real = Yte * ys + ym
    ss_res = ((pred_real - Yte_real) ** 2).sum(0)
    ss_tot = ((Yte_real - Yte_real.mean(0)) ** 2).sum(0) + 1e-9
    r2 = 1 - ss_res / ss_tot
    print(f"frames={len(X)}  state_dim={X.shape[1]}  action_dim={Y.shape[1]}")
    print(f"BC test MSE (norm) = {bc_mse:.4f}   predict-mean baseline = {base_mse:.4f}   "
          f"improvement = {base_mse / max(bc_mse,1e-9):.1f}x")
    print(f"per-joint R^2 = {[round(float(v),3) for v in r2]}")
    print("LEARNABLE ✅" if bc_mse < 0.25 * base_mse else "weak — needs more/cleaner data")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
