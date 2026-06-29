"""Shared helpers for genre pipelines: build-ops, vectors, config baking."""
from __future__ import annotations

import re
from typing import Any

from .emit.common import hex_to_rgb

VEC3 = {
    "type": "object", "additionalProperties": False,
    "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
    "required": ["x", "y", "z"],
}


def xyz(v: Any, default=(0.0, 4.0, 0.0)) -> list:
    if isinstance(v, dict):
        return [round(float(v.get("x", default[0])), 2),
                round(float(v.get("y", default[1])), 2),
                round(float(v.get("z", default[2])), 2)]
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return [round(float(v[0]), 2), round(float(v[1]), 2), round(float(v[2]), 2)]
    return [float(default[0]), float(default[1]), float(default[2])]


def _rgb(color, default=(154, 160, 166)):
    if isinstance(color, str):
        return list(hex_to_rgb(color))
    if isinstance(color, (list, tuple)) and len(color) == 3:
        return [int(color[0]), int(color[1]), int(color[2])]
    return list(default)


def op(folder: str, name: str, pos, size, color, material: str = "SmoothPlastic",
       cc: bool = True, klass: str = "Part", shape: str = "Block",
       rot: float = 0.0, light=None) -> dict:
    d = {"folder": folder, "class": klass, "name": name,
         "pos": xyz(pos), "size": xyz(size, (4, 1, 4)),
         "color": _rgb(color), "material": material, "cc": cc}
    if shape and shape != "Block":
        d["shape"] = shape
    if rot:
        d["rot"] = round(float(rot), 1)
    if light:
        d["light"] = {"color": _rgb(light.get("color", color)),
                      "brightness": float(light.get("brightness", 2)),
                      "range": float(light.get("range", 16))}
    return d


def emit_ev(cb, type_: str, **data) -> None:
    if cb:
        try:
            cb({"type": type_, **data})
        except Exception:
            pass


_MENTION_RE = re.compile(r"@([A-Za-z][\w-]*)")


def post_channel(cb, agent_id: str, name: str, text: str) -> None:
    """Post a message to the shared agent channel (Slack-style), with @mentions parsed out."""
    emit_ev(cb, "channel", id=agent_id, name=name, text=text, mentions=_MENTION_RE.findall(text))


async def voice(client, cb, agent_id: str, name: str, role: str, did: str, team: str = "") -> None:
    """Have the agent that just finished SPEAK for real — an LLM writes ITS message from its actual
    work, passing the concrete details a teammate needs, handing off, or asking a question. It may
    @mention one or several teammates. Falls back to the raw context if the call fails."""
    try:
        sys = (f"You are {name}, the {role} on an AI game-studio team, posting in the team's #agents "
               f"channel. Based on what you just did (below), write ONE message to the team that does "
               f"something USEFUL: pass along the concrete details a teammate will need (real names, "
               f"values, IDs, coordinates), hand off the next step, or ask a specific question. "
               f"@mention the exact teammate(s) who need it — one or several. Be precise, not chatty. "
               f"Under ~40 words. No surrounding quotes."
               + (f"\nTeammates you can @mention: {team}." if team else ""))
        t = await client.chat([{"role": "system", "content": sys},
                               {"role": "user", "content": did}], max_tokens=130, temperature=0.7)
        msg = (t.text or "").strip().strip('"').strip()
        post_channel(cb, agent_id, name, msg or did[:160])
    except Exception:
        post_channel(cb, agent_id, name, did[:160])


def lua_value(v: Any) -> str:
    """Serialize a Python value into a Luau literal (for baked CONFIG tables)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(lua_value(x) for x in v) + "}"
    if isinstance(v, dict):
        parts = []
        for k, val in v.items():
            key = str(k)
            if key.isidentifier():
                parts.append(f"{key} = {lua_value(val)}")
            else:
                parts.append(f'["{key}"] = {lua_value(val)}')
        return "{" + ", ".join(parts) + "}"
    return "nil"
