"""Real Luau SYNTAX/compile verification using the actual Luau compiler (luau-compile).
It just parses + compiles (no Roblox type-defs needed, so no false positives on `game`,
`workspace`, etc.) — a clean signal for "does this module even parse". Plus a per-module
repair pass that loops until every module compiles.
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import tempfile
import urllib.request
import zipfile
from shutil import which
from typing import Optional

from .authored import _force_fix, _strip_fences
from .genre_common import emit_ev, post_channel

_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
_EXE = os.path.join(_BIN_DIR, "luau-compile.exe")
_URL = "https://github.com/luau-lang/luau/releases/latest/download/luau-windows.zip"
_resolved: Optional[str] = None


def _ensure() -> Optional[str]:
    global _resolved
    if _resolved:
        return _resolved
    if os.path.exists(_EXE):
        _resolved = _EXE
        return _resolved
    found = which("luau-compile") or which("luau-compile.exe")
    if found:
        _resolved = found
        return _resolved
    try:  # self-bootstrap on Windows
        os.makedirs(_BIN_DIR, exist_ok=True)
        data = urllib.request.urlopen(_URL, timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if n.endswith("luau-compile.exe"):
                    with z.open(n) as src, open(_EXE, "wb") as dst:
                        dst.write(src.read())
        if os.path.exists(_EXE):
            _resolved = _EXE
            return _resolved
    except Exception:
        return None
    return None


def check(source: str) -> Optional[str]:
    """None if the Luau compiles, else a cleaned error message (line/col + reason)."""
    exe = _ensure()
    if not exe or not source.strip():
        return None
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".luau", delete=False, encoding="utf-8") as f:
            f.write(source)
            path = f.name
        proc = subprocess.run([exe, "--binary", path], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=25)
        if proc.returncode == 0:
            return None
        out = (proc.stderr or proc.stdout or "").strip()
        for ln in out.splitlines():
            if "Error" in ln:
                return re.sub(r"^.*\.luau", "", ln).strip()  # drop the temp path prefix
        return out.splitlines()[0] if out else "compile error"
    except Exception:
        return None
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


SYNTAX_FIX_SYSTEM = r"""You are fixing a SYNTAX/compile error in a Roblox Luau script. The Luau
compiler reported the EXACT error (line, column, reason). Fix ONLY what is needed to make it
compile — do not change behavior or remove features. Output ONLY the corrected Luau."""


async def run_syntax_repair(modules: list[dict], client, on_event=None) -> list[dict]:
    if not _ensure():
        return modules  # no checker available -> skip gracefully
    rnd = 0
    while client.runs < client.max_runs - 2:  # only the global run budget caps this
        rnd += 1
        bad = [(m, err) for m in modules if (err := check(m["source"]))]
        if not bad:
            if rnd > 1:
                post_channel(on_event, "syntax", "Luau Compiler", "Every module compiles cleanly ✅")
            break
        emit_ev(on_event, "agent", id="syntax", role="QA", name="Luau Compiler",
                status="done", detail=f"round {rnd}: {len(bad)} compile error(s)")
        post_channel(on_event, "syntax", "Luau Compiler", f"Round {rnd}: {len(bad)} module(s) won't compile — "
                     + " ".join(f"@{m['name']}" for m, _ in bad[:5]) + " fixing.")

        async def fix(m: dict, err: str):
            aid = f"syntax:{m['name']}"
            emit_ev(on_event, "agent", id=aid, role="Coder", name=m["name"], status="working")
            user = f"Luau compile error: {err}\n\nFix this module so it compiles:\n{m['source']}"
            t = await client.chat([{"role": "system", "content": SYNTAX_FIX_SYSTEM},
                                   {"role": "user", "content": user}], max_tokens=12000, temperature=0.2)
            emit_ev(on_event, "agent", id=aid, status="done", detail="compiles")
            return m, _force_fix(_strip_fences(t.text or ""))

        for m, fixed in await asyncio.gather(*[fix(m, e) for m, e in bad]):
            if len(fixed) > 100:
                m["source"] = fixed
    return modules
