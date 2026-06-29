"""Deterministic cross-module integration verifier. The LLM integration pass can miss
things; this MECHANICALLY checks that the modules actually agree on the shared interface:
- every RemoteEvent a module uses exists (we union used remotes into the bootstrap);
- every shared-state ATTRIBUTE that is read is written somewhere (catches name mismatches
  like reader "Gold" vs writer "PlayerGold");
- every CollectionService TAG queried is added somewhere (catches towers looking for "Enemy"
  that the spawner never tags);
- every required shared ModuleScript exists.
Returns precise, actionable issues for the repair loop, and the set of remotes actually used.
"""
from __future__ import annotations

import re

_SETATTR = re.compile(r':SetAttribute\(\s*"([^"]+)"')
_GETATTR = re.compile(r':GetAttribute(?:ChangedSignal)?\(\s*"([^"]+)"')
_ADDTAG = re.compile(r':AddTag\([^,]+,\s*"([^"]+)"')
_USETAG = re.compile(r':(?:GetTagged|HasTag|GetInstanceAddedSignal|GetInstanceRemovedSignal)\(\s*"([^"]+)"')
_REQ_SHARED = re.compile(r'G4Shared[.:]\s*(?:WaitForChild\(\s*")?(\w+)')
_REMOTE_DECL = re.compile(r'local\s+(\w+)\s*=\s*[\w.]+[:.]\s*(?:WaitForChild|FindFirstChild)\(\s*"([^"]+)"\s*\)')
_REMOTE_METHODS = ("FireServer", "FireClient", "FireAllClients", "OnServerEvent", "OnClientEvent",
                   "InvokeServer", "InvokeClient", "OnServerInvoke", "OnClientInvoke")


def _remotes_used(src: str) -> set[str]:
    used = set()
    for var, name in _REMOTE_DECL.findall(src):
        if re.search(rf'\b{re.escape(var)}\b[:.]\s*(?:{"|".join(_REMOTE_METHODS)})', src):
            used.add(name)
    return used


def _exports_of(src: str) -> set | None:
    """The top-level members a shared ModuleScript exports, or None if undeterminable."""
    rets = re.findall(r'^\s*return\s+(\w+)\b', src, re.M)
    tbl = rets[-1] if rets else None
    if not tbl:
        return None
    ex = set(re.findall(rf'\b{re.escape(tbl)}\.(\w+)\s*=', src))
    ex |= set(re.findall(rf'function\s+{re.escape(tbl)}[.:](\w+)', src))
    return ex


def _shared_aliases(src: str, shared_names: set) -> dict:
    out = {}
    for m in re.finditer(r'local\s+(\w+)\s*=\s*require\(([^\n]*)\)', src):
        alias, expr = m.group(1), m.group(2)
        if "G4Shared" not in expr:
            continue
        for nm in shared_names:
            if re.search(rf'["\.]{re.escape(nm)}\b', expr):
                out[alias] = nm
                break
    return out


def _shared_api_issues(modules: list[dict]) -> list[dict]:
    """Flag a system calling Config.Func when the shared Config module doesn't export Func —
    this silently crashes start() and the system never runs."""
    shared = {m["name"]: m for m in modules if m["kind"] == "shared"}
    exports = {}
    for nm, m in shared.items():
        ex = _exports_of(m["source"])
        if ex is not None:
            exports[nm] = ex
    issues = []
    for m in modules:
        if m["kind"] == "shared":
            continue
        for alias, modname in _shared_aliases(m["source"], set(shared)).items():
            if modname not in exports:
                continue
            for member in set(re.findall(rf'\b{re.escape(alias)}\.(\w+)\b', m["source"])):
                if member not in exports[modname]:
                    issues.append({
                        "modules": [m["name"], modname],
                        "detail": f'{m["name"]} uses {alias}.{member} but '
                                  f'ReplicatedStorage.G4Shared.{modname} does NOT export "{member}". '
                                  f'{modname} exports: {sorted(exports[modname])}. Either add {member} '
                                  f'to {modname} or call the correct existing name.'})
    return issues


def verify(spec: dict, modules: list[dict]) -> tuple[list[dict], set[str]]:
    writes: dict[str, set] = {}
    reads: dict[str, set] = {}
    tags_add: dict[str, set] = {}
    tags_use: dict[str, set] = {}
    remotes_used: set[str] = set()
    shared_names = {m["name"] for m in modules if m["kind"] == "shared"}
    requires: dict[str, set] = {}

    for m in modules:
        src, nm = m["source"], m["name"]
        for a in _SETATTR.findall(src):
            writes.setdefault(a, set()).add(nm)
        for a in _GETATTR.findall(src):
            reads.setdefault(a, set()).add(nm)
        for t in _ADDTAG.findall(src):
            tags_add.setdefault(t, set()).add(nm)
        for t in _USETAG.findall(src):
            tags_use.setdefault(t, set()).add(nm)
        remotes_used |= _remotes_used(src)
        requires[nm] = set(_REQ_SHARED.findall(src)) - {"WaitForChild"}

    issues: list[dict] = []
    for a, mods in reads.items():
        if a not in writes:
            issues.append({
                "modules": sorted(mods),
                "detail": f'attribute "{a}" is READ by {sorted(mods)} but NO module SetAttribute("{a}"). '
                          f'Attributes that ARE set somewhere: {sorted(writes) or "none"}. '
                          f'Reconcile to a single shared name.'})
    for t, mods in tags_use.items():
        if t not in tags_add:
            issues.append({
                "modules": sorted(mods),
                "detail": f'CollectionService tag "{t}" is queried by {sorted(mods)} but NO module '
                          f'AddTag()s it. Tags that ARE added: {sorted(tags_add) or "none"}.'})
    for nm, reqs in requires.items():
        for r in reqs:
            if r not in shared_names:
                issues.append({
                    "modules": [nm],
                    "detail": f'{nm} requires ReplicatedStorage.G4Shared.{r}, which does NOT exist. '
                              f'Existing shared modules: {sorted(shared_names)}.'})
    issues += _shared_api_issues(modules)  # calls to non-existent shared-module functions
    return issues, remotes_used
