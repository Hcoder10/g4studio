# G4 Studio: Roblox as a robot-data factory using Gemma 4

**Point Gemma-4 at a robot arm. It invents fun games where *playing is labeling robot training
data***, and keeps inventing harder ones as players get good. The arm is a faithful, URDF-exact
**SO-101**; every session records LeRobot-format joint-space demonstrations.

Built on **Gemma-4-31b** running on **Cerebras** (each design/repair call ~100 ms, so a whole game
is invented, coded, syntax-repaired and packaged in seconds by the team of gemma 4 agents in the harness I made tuned to its strengths, around ~150x faster than on my gpu, even when I quantize it!).

---

## The idea

Manipulation data is the bottleneck in robot learning, and it's expensive to collect (VERY expensive). G4 Studio
turns it into *gameplay*: Gemma designs a game whose win condition can only be met by controlling
the arm well, so a kid playing a claw-machine game is generating clean, **skill-labeled** SO-101
demonstrations. 

## What's real (what's done)

| Piece | Status |
|---|---|
| **SO-101 arm** | Reconstructed from the official URDF, that means exact joint origins/axes/limits, real meshes baked per-link. DLS IK + null-space posture. |
| **Game generation** | Gemma designs + codes games that compile; verified across many (color-sort, stacking, insertion, claw-machine…). |
| **Self-extending curriculum** | Master a game (2-win streak) means that Gemma forges a harder one in the same skill, hot-swapped at runtime via `loadstring` in just a few seconds (cerebras is coming in handy for that realtime game gen, so it never ends!) |
| **Structured task families** | 5 families (pick_place / sorting / stacking / insertion / kitting) with variation axes + a dedup registry. 3 stacking games came out distinct (taper / inverted-weight / thin-slab). |
| **LeRobot-native data** | `observation.state` = joint angles, `action` = commanded joint targets; exports to LeRobot v2.1 (parquet + meta). |
| **Dataset** | **192 episodes / 73k frames**, all LeRobot v2.1 — **42 from real human play** across **13** Gemma-invented games, plus **150 synthetic** episodes for scale. |
| **Learnability** | A behavior-cloning smoke test cleanly recovers the recorded policy (per-joint **R² 0.94–1.0**; on the synthetic set, **19× below** a tough predict-current-state baseline / 48× below predict-mean). The 42 human demos are the proof-of-loop seed. In the future, we would correct jitters and artifacts produced by the Roblox Engine. |
| **Onboard any robot** | `onboard_robot.py <urdf>` auto-derives the chain + **auto-searches a rest pose** by reach, in seconds — generic to any URDF. Reproduced on the SO-101 → **93% forward-workspace reach**. |

## Honest limits (what's to come in the future)

- **Sim-to-real:** it's Roblox *kinematic* physics, not real dynamics. The data is validated as
  *learnable* and *correctly formatted*, not as zero-shot transferable. Treat it as sim
  pretraining / curriculum data. In the future, we would implement PhysX to make this more accurate.
- **Data scale:** the 42 human-play episodes prove the play→data loop end-to-end; the headline
  learnability numbers are on the synthetic set (a clean scripted policy). The human corpus is an
  early seed, not yet a strongly learned skill on its own. We don't have enough players yet, so it's hard to get more until this project scales!
- **IK coverage:** the 5-DOF arm can't reach every pose; games place objects in the reliable
  forward workcell (where the IK solves to ~0 error). This is ideal for Roblox. In the future, we would cater to a primarily VR audience so we can get full realistic teleop-like data.
- **Mesh upload** during onboarding is manual (Roblox's importer; no external tool can automate it).
- The runtime `loadstring` hot-swap needs *LoadStringEnabled* and is the one path not yet driven
  end-to-end in Studio. They are just few minute changes whenever you want to change the robot that's being used, its easily changed.

---

Thanks for reading, Judges! Hopefully this strikes you as interesting, as it's a problem I've been thinking about and researching for a while, and I believe that real-time game gen is an important part of it. Thanks to you guys for hosting this, otherwise this would've been very hard to make (with gpu based providers).

## Quick start

```bash
pip install -r requirements.txt
echo "CEREBRAS_API_KEY=..." > .env          # gitignored, never commit
python backend/server.py                     # http://127.0.0.1:8000

# 1) Gemma invents a robot game (or pass a structured family):
python roblox/robots/make_game.py "claw machine prizes"
curl -X POST :8000/api/robotgame -d '{"family":"stacking"}'   # -> out/G4RobotGame.rbxmx
# Insert out/G4RobotGame.rbxmx into Workspace, enable HTTP Requests, Play.

# 2) Data pipeline (works without Studio, using synthesized demos):
python backend/tools/synth_traces.py 150     # scripted policy -> datasets/*.jsonl
python backend/tools/lerobot_export.py        # -> lerobot_datasets/<task>/ (LeRobot v2.1)
python backend/tools/bc_smoke.py              # prove the data is learnable

# 3) Onboard a new arm:
python backend/tools/onboard_robot.py path/to/robot.urdf myarm
```

## Layout

- `roblox/robots/` — the robot kit: `SO101.lua` (URDF-exact arm + IK), `Trace.lua` (recorder),
  `kit/Harness.server.lua` (drives a Gemma game, records traces, runs the curriculum),
  `kit/Control.client.lua` (hover controller), `build_game_rbxmx.py` (packager), `meshes/`.
- `backend/g4studio/robotgame.py` — Director/Coder game generation + extend + family generation.
- `backend/g4studio/families.py` — structured task families + dedup registry.
- `backend/tools/` — `so101_kin.py` (Python kinematics), `synth_traces.py`, `lerobot_export.py`,
  `bc_smoke.py`, `onboard_robot.py`.
- `backend/server.py` — API: `/api/robotgame`, `/api/robotgame/extend`, `/api/families`,
  `/api/trace`, `/api/datasets`.
- `backend/g4studio/` (rest) — the original Gemma "build a playable Roblox game from a prompt"
  studio this grew out of (authored + swarm pipelines). Try this out if you want to make games OTHER than robot data collection ones. it is really good!.
