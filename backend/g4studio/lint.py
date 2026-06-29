"""Deterministic runtime-footgun linter for the generated modules — bugs that COMPILE
fine but break at runtime. Two parts:
- autofix(): safe mechanical modernizations applied to every module (wait->task.wait, etc.).
- lint(): detect structural runtime bugs (client-only API in a server module; an unbounded
  `while true do` with no yield) -> LLM repair loop.
"""
from __future__ import annotations

import asyncio
import re

from .authored import _force_fix, _strip_fences
from .genre_common import emit_ev

# --- safe mechanical modernizations (deprecated/throttled -> correct) ---
_SUBS = [
    (re.compile(r'(?<![\w.:])wait\s*\('), 'task.wait('),
    (re.compile(r'(?<![\w.:])spawn\s*\('), 'task.spawn('),
    (re.compile(r'(?<![\w.:])delay\s*\('), 'task.delay('),
    (re.compile(r':connect\s*\('), ':Connect('),
    (re.compile(r':wait\s*\('), ':Wait('),
]


def autofix(src: str) -> str:
    for rx, rep in _SUBS:
        src = rx.sub(rep, src)
    return src


# --- structural runtime bugs (need understanding -> LLM repair) ---
_CLIENT_ONLY = [
    (re.compile(r'\bLocalPlayer\b'), "LocalPlayer"),
    (re.compile(r':GetMouse\s*\('), "Player:GetMouse()"),
    (re.compile(r'\bUserInputService\b'), "UserInputService"),
    (re.compile(r'\bRenderStepped\b'), "RunService.RenderStepped"),
    (re.compile(r'\bContextActionService\b'), "ContextActionService"),
]
_YIELD = re.compile(r'task\.wait|:Wait\(|\bwait\(')


def lint(modules: list[dict]) -> list[dict]:
    issues = []
    for m in modules:
        src, nm, side = m["source"], m["name"], m["kind"]
        if side == "server":
            for rx, label in _CLIENT_ONLY:
                if rx.search(src):
                    issues.append({"module": nm, "detail":
                        f'{nm} is a SERVER module but uses the CLIENT-ONLY API "{label}" (the server '
                        f'has no LocalPlayer / mouse / input / render step). Restructure: a CLIENT '
                        f'reads the input and sends a RemoteEvent; keep only server-authoritative '
                        f'logic here.'})
                    break
        if re.search(r'while\s+true\s+do', src) and not _YIELD.search(src):
            issues.append({"module": nm, "detail":
                f'{nm} has a `while true do` loop with NO task.wait inside — it will freeze the game. '
                f'Add a task.wait() in every unbounded loop.'})
    return issues


LINT_FIX_SYSTEM = r"""You are fixing a RUNTIME bug in one Roblox Luau module (it compiles, but would
misbehave at runtime). Apply the fix described, keeping all features. Only REAL Roblox API. Output
ONLY the corrected Luau."""


async def run_lint_repair(modules: list[dict], client, on_event=None, rounds: int = 2) -> list[dict]:
    # deterministic modernizations first
    for m in modules:
        m["source"] = autofix(m["source"])

    for rnd in range(rounds):
        issues = lint(modules)
        if not issues:
            break
        emit_ev(on_event, "agent", id="lint", role="QA", name="Runtime Linter",
                status="done", detail=f"round {rnd + 1}: {len(issues)} runtime issue(s)")
        by_mod: dict[str, list[str]] = {}
        for iss in issues:
            by_mod.setdefault(iss["module"], []).append(iss["detail"])
        by_name = {m["name"]: m for m in modules}

        async def fix(mname: str, details: list[str]):
            m = by_name.get(mname)
            if not m:
                return None
            aid = f"lint:{mname}"
            emit_ev(on_event, "agent", id=aid, role="Coder", name=mname, status="working")
            user = ("RUNTIME BUGS to fix:\n- " + "\n- ".join(details) +
                    f"\n\nMODULE ({m['kind']}):\n{m['source']}\n\nOutput the corrected module.")
            t = await client.chat([{"role": "system", "content": LINT_FIX_SYSTEM},
                                   {"role": "user", "content": user}], max_tokens=12000, temperature=0.3)
            emit_ev(on_event, "agent", id=aid, status="done", detail="fixed")
            return mname, autofix(_force_fix(_strip_fences(t.text or "")))

        for res in await asyncio.gather(*[fix(mn, d) for mn, d in by_mod.items()]):
            if res and len(res[1]) > 100:
                by_name[res[0]]["source"] = res[1]
    return modules
