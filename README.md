# G4 Studio — an AI game studio at the speed of thought

A swarm of **Gemma-4-31b** agents running on **Cerebras** turns one prompt into a
complete, **playable Roblox obby in seconds**. A vision agent *sees* the level and
fixes it. Built for the Cerebras × Google DeepMind Gemma 4 hackathon.

## Why it's fast (and real)
- **Cerebras Gemma-4** runs each agent call in ~100 ms, so a whole multi-agent
  studio (Director → Builders → Scripter → Vision Playtester) resolves in seconds.
- The swarm emits **structured build-ops**, which become a real, **insertable
  Roblox model** (`.rbxmx`) with working scripts embedded — Insert From File, press
  Play. No live-Studio bridge required.
- **Templated mechanics + LLM-designed layout:** Gemma does the creative/spatial
  design; proven Luau templates guarantee checkpoints, kill-bricks, win detection,
  and moving platforms work every time.

## Architecture
```
prompt
  │
  ▼
Director (Gemma-4)  ── game spec (theme, difficulty, stage plan)
  │
  ├─► Builder agents (parallel)  ── structured build-ops (platforms, hazards, …)
  ├─► Scripter                   ── mechanics params
  ▼
GameSpec ──► emit/rbxmx.py  ──► g4obby.rbxmx  (Insert into Studio → playable)
         └─► emit/luau.py   ──► g4obby_build.luau (command-bar fallback)
         └─► three.js preview (browser) ── live block-by-block build = the speed shot
  │
  ▼
Vision Playtester (Gemma-4 vision) ── screenshots the preview, critiques, fixes
```

## Layout
- `backend/g4studio/ops.py` — GameSpec + build-op schema
- `backend/g4studio/mechanics.py` — templated Luau mechanics (model-agnostic)
- `backend/g4studio/emit/` — `.rbxmx` (primary) + Luau emitters
- `backend/g4studio/cerebras.py` — async Gemma-4 client (chat / tools / vision / timing)
- `backend/sample_obby.py` — offline demo: hand-authored spec → artifacts (no API key)
- `frontend/` — live swarm UI + three.js preview + speed side-by-side

## Quick start (offline, no key)
```
python backend/sample_obby.py
# → out/g4obby.rbxmx  and  out/g4obby_build.luau
# In Studio: right-click Workspace → Insert From File → out/g4obby.rbxmx → Play
```

Put your key in a gitignored `.env` (`CEREBRAS_API_KEY=...`). Never commit it.
