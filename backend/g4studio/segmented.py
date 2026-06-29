"""The segmented harness: prompt -> Architect (spec) -> RAG asset resolution ->
parallel module builders -> deterministic integrator. Produces a multi-script game.
General-purpose (any game); the TD benchmark is just the hardest target.
"""
from __future__ import annotations

import time

from .architect import resolve_assets, run_architect
from .builder import run_modules
from .cerebras import CerebrasClient
from .genre_common import emit_ev
from .integrate import assemble
from .integration import run_integration_qa, run_verify_repair


async def run_segmented(prompt: str, client: CerebrasClient, on_event=None) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    spec, _ = await run_architect(prompt, client, on_event)
    resolved = resolve_assets(spec, k=2)
    modules = await run_modules(spec, resolved, client, on_event)
    # holistic pass: one reviewer sees ALL modules, decides conventions, fixes how they connect
    modules = await run_integration_qa(spec, modules, client, on_event)
    # mechanical guarantee: verify the modules agree (attrs/tags/remotes/requires) -> repair -> repeat
    modules = await run_verify_repair(spec, modules, client, on_event)
    # final gate: every module must actually COMPILE (real Luau compiler) -> repair -> repeat
    from .syntax import run_syntax_repair
    modules = await run_syntax_repair(modules, client, on_event)
    build = assemble(spec, modules)

    total_lines = sum(m["source"].count("\n") + 1 for m in modules)
    metrics = {
        "genre": "segmented", "name": build["name"],
        "systems": len(build["systems"]), "shared": len(build["shared"]),
        "modules": len(modules), "lines": total_lines,
        "assets_used": sum(len(v) for v in resolved.values()),
        "wall_ms": round((time.perf_counter() - t0) * 1000.0),
    }
    emit_ev(on_event, "segmented_done", name=build["name"],
            systems=metrics["systems"], lines=total_lines, wall_ms=metrics["wall_ms"])
    return build, metrics
