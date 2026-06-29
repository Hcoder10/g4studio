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
    return issues, remotes_used
