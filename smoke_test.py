"""
Genesis smoke test — validates everything the swarm depends on, in one run:
  1) text completion + tokens/sec (the speed pitch)
  2) tool-calling with strict structured output (how the swarm emits build-ops)
  3) vision (image_url base64) — the multimodal playtester path

Usage (PowerShell):
    $env:CEREBRAS_API_KEY = "csk-..."
    python C:\Users\sarta\g4studio\smoke_test.py

Only dependency: requests  (pip install requests). PIL is optional (better vision test).
"""

import base64
import io
import json
import os
import time

import requests

BASE_URL = "https://api.cerebras.ai/v1/chat/completions"
MODEL = "gemma-4-31b"

# Candidate .env files (gitignored). Put the key in any ONE of these:
#   CEREBRAS_API_KEY=csk-...
_ENV_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), ".env"),
    r"C:\Users\sarta\roblox-studio-mcp\.env",
    r"C:\Users\sarta\roblox-studio-mcp\packages\agent-harness\.env",
]


def load_api_key():
    """Return the key from the environment, else from a gitignored .env file.
    The raw key is never printed."""
    val = os.environ.get("CEREBRAS_API_KEY")
    if val:
        return val.strip()
    for path in _ENV_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("CEREBRAS_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return None


API_KEY = load_api_key()
if not API_KEY:
    raise SystemExit(
        "No CEREBRAS_API_KEY found. Add a line `CEREBRAS_API_KEY=csk-...` to "
        "C:\\Users\\sarta\\roblox-studio-mcp\\packages\\agent-harness\\.env "
        "(gitignored), or set $env:CEREBRAS_API_KEY for this shell."
    )
print(f"(CEREBRAS_API_KEY loaded, length {len(API_KEY)} — not displayed)")

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def call(payload, label):
    t0 = time.time()
    r = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=120)
    dt = time.time() - t0
    if r.status_code != 200:
        print(f"\n[{label}] HTTP {r.status_code}\n{r.text[:1000]}")
        r.raise_for_status()
    data = r.json()
    usage = data.get("usage", {})
    ti = data.get("time_info", {}) or {}
    ctoks = usage.get("completion_tokens", 0)
    # tokens/sec: prefer server timing if present, else wall clock
    gen_t = ti.get("completion_time") or dt
    tps = (ctoks / gen_t) if gen_t else 0
    print(f"\n=== {label} ===")
    print(f"  wall: {dt*1000:.0f} ms | completion_tokens: {ctoks} | ~{tps:.0f} tok/s")
    if ti:
        print(f"  time_info: {json.dumps(ti)}")
    return data


# ---------- 1) TEXT + SPEED ----------
txt = call(
    {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "In one sentence, what makes a great Roblox obby fun?"}
        ],
        "max_tokens": 120,
    },
    "1. text + speed",
)
print("  ->", txt["choices"][0]["message"]["content"].strip())


# ---------- 2) TOOL CALLING / STRUCTURED BUILD-OP ----------
# This is the shape the swarm uses to emit deterministic build operations.
tools = [
    {
        "type": "function",
        "function": {
            "name": "create_part",
            "description": "Create a Roblox BasePart in the workspace.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "shape": {"type": "string", "enum": ["Block", "Ball", "Cylinder", "Wedge"]},
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                    },
                    "size": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                    },
                    "color": {"type": "string", "description": "BrickColor or hex"},
                    "anchored": {"type": "boolean"},
                },
                "required": ["name", "shape", "position", "size", "color", "anchored"],
            },
        },
    }
]
tool_resp = call(
    {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You build Roblox obbies. Use create_part to place a single neon-blue floating checkpoint platform at height 20.",
            },
            {"role": "user", "content": "Place the first checkpoint platform."},
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 300,
    },
    "2. tool-calling (build-op)",
)
msg = tool_resp["choices"][0]["message"]
calls = msg.get("tool_calls") or []
if calls:
    fn = calls[0]["function"]
    print(f"  -> tool: {fn['name']}")
    print(f"  -> args: {fn['arguments']}")
    try:
        json.loads(fn["arguments"])
        print("  -> args parse: OK (valid JSON)")
    except Exception as e:
        print(f"  -> args parse: FAILED ({e})")
else:
    print("  -> NO tool_call returned. content:", (msg.get("content") or "")[:300])


# ---------- 3) VISION (multimodal playtester path) ----------
def make_test_image_b64():
    """Draw '42' on a colored canvas if PIL is available; else a 1x1 pixel."""
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (200, 120), (20, 30, 60))
        d = ImageDraw.Draw(img)
        d.rectangle([10, 10, 190, 110], outline=(0, 220, 255), width=4)
        d.text((70, 45), "42", fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode(), "drew '42' on dark-blue canvas"
    except Exception:
        # 1x1 red pixel fallback — only confirms the request shape is accepted
        px = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAA"
            "C0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        return px, "1x1 red pixel (install Pillow for a real vision test)"


b64, note = make_test_image_b64()
print(f"\n(vision test image: {note})")
vis = call(
    {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What number and what border color do you see? Answer briefly."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }
        ],
        "max_tokens": 80,
    },
    "3. vision (multimodal)",
)
print("  ->", vis["choices"][0]["message"]["content"].strip())

print("\nALL THREE PATHS HIT. If tokens/sec is in the hundreds+, the speed pitch is real.")
