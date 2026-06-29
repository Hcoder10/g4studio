"""Team channel for the build agents (Coder / Builder / Reviewer / Vision-QA).

Posts to a real Slack channel via an incoming webhook (SLACK_WEBHOOK_URL) when configured, and always
mirrors to the in-app on_event stream + an in-memory transcript. Enforces a per-direction PING cap so
the agents can't @-spam each other (the Reviewer/Builder may ping the Coder at most `max_pings` times).
"""
import json
import os
import urllib.request
from typing import Callable, Optional

AGENTS = {
    "coder":    {"emoji": ":technologist:",        "name": "Coder"},
    "builder":  {"emoji": ":hammer_and_wrench:",   "name": "Builder"},
    "reviewer": {"emoji": ":mag:",                  "name": "Reviewer"},
    "qa":       {"emoji": ":eyes:",                 "name": "Vision QA"},
}


class Channel:
    """One #channel for building one game. `max_pings` caps @-mentions per (from -> to) direction."""

    def __init__(self, topic: str = "build", on_event: Optional[Callable] = None, max_pings: int = 2):
        self.url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
        self.on_event = on_event
        self.topic = topic
        self.max_pings = max_pings
        self.transcript: list[dict] = []
        self._pings: dict[tuple[str, str], int] = {}

    def post(self, who: str, text: str, mention: Optional[str] = None) -> None:
        a = AGENTS.get(who, {"emoji": "", "name": who})
        to_name = AGENTS.get(mention, {}).get("name", mention) if mention else None
        shown = (f"@{to_name} " if to_name else "") + text
        self.transcript.append({"who": a["name"], "text": shown, "mention": mention})
        if self.on_event:
            try:
                self.on_event({"type": "slack", "topic": self.topic, "who": a["name"], "text": shown})
            except Exception:
                pass
        if self.url:
            payload = {
                "username": f"{a['name']} · #{self.topic}",
                "icon_emoji": a["emoji"],
                "text": (f"*@{to_name}* " if to_name else "") + text,
            }
            try:
                req = urllib.request.Request(
                    self.url, data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=8)
            except Exception:
                pass  # never let a channel hiccup break the build

    def can_ping(self, frm: str, to: str) -> bool:
        return self._pings.get((frm, to), 0) < self.max_pings

    def ping(self, frm: str, to: str, text: str) -> bool:
        """@-ping `to` from `frm` if still under the cap. Returns False (and says so) once capped."""
        if not self.can_ping(frm, to):
            self.post(frm, f"(ping limit reached with @{AGENTS.get(to, {}).get('name', to)} — "
                           f"proceeding without another round)")
            return False
        self._pings[(frm, to)] = self._pings.get((frm, to), 0) + 1
        self.post(frm, text, mention=to)
        return True
