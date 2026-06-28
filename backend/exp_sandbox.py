"""Test the Luau sandbox on real authored scripts: run -> recover parts -> render."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from g4studio.sandbox import run_world  # noqa: E402
from g4studio.render import render_build  # noqa: E402

out_dir = os.path.join(os.path.dirname(__file__), "..", "out")
files = sorted(glob.glob(os.path.join(out_dir, "authored_*.lua"))) + \
    [os.path.join(out_dir, "worldcode.lua")]

for f in files:
    if not os.path.exists(f):
        continue
    src = open(f, encoding="utf-8").read()
    build, err = run_world(src)
    n = len(build["parts"])
    print(f"{os.path.basename(f):20s} parts={n:4d}  err={err or 'none'}")
    if n > 5:
        png = render_build(build)
        outpng = f.replace(".lua", "_render.png")
        open(outpng, "wb").write(png)
        print(f"   -> rendered {os.path.basename(outpng)}")
