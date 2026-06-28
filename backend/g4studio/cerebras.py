"""Async Gemma-4-31b client for Cerebras (OpenAI-compatible).

Thin, fast, and built around the hackathon's three needs:
  - chat() with tool-calling for structured build-ops
  - json() for strict structured outputs (the Director's game spec)
  - vision via image content blocks (the playtester)
Every call records latency + tokens/sec so the UI can show the speed story.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

_ENV_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
    r"C:\Users\sarta\g4studio\.env",
]


def load_key() -> Optional[str]:
    val = os.environ.get("CEREBRAS_API_KEY")
    if val:
        return val.strip()
    for path in _ENV_CANDIDATES:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("CEREBRAS_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return None


@dataclass
class Turn:
    text: Optional[str]
    tool_calls: list  # [{"name": str, "args": dict, "id": str}]
    usage: dict
    latency_ms: float
    raw: dict = field(default_factory=dict)

    @property
    def completion_tokens(self) -> int:
        return int(self.usage.get("completion_tokens", 0))

    @property
    def tokens_per_sec(self) -> float:
        secs = self.latency_ms / 1000.0
        return self.completion_tokens / secs if secs > 0 else 0.0


class CerebrasClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.6,
        max_tokens: int = 8000,
        reasoning_effort: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or load_key()
        if not self.api_key:
            raise RuntimeError("No CEREBRAS_API_KEY (set env or .env).")
        self.base_url = (base_url or os.environ.get("CEREBRAS_BASE_URL")
                         or "https://api.cerebras.ai/v1").rstrip("/")
        self.model = model or os.environ.get("GEMMA_MODEL", "gemma-4-31b")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort or os.environ.get(
            "CEREBRAS_REASONING_EFFORT", "none")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    async def _post(self, body: dict) -> tuple[dict, float]:
        t0 = time.perf_counter()
        r = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=body,
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if r.status_code != 200:
            raise RuntimeError(f"Cerebras {r.status_code}: {r.text[:400]}")
        return r.json(), dt_ms

    def _base_body(self, messages: list, max_tokens: Optional[int]) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if self.reasoning_effort and self.reasoning_effort != "none":
            body["reasoning_effort"] = self.reasoning_effort
        return body

    async def chat(self, messages: list, tools: Optional[list] = None,
                   tool_choice: str = "auto", max_tokens: Optional[int] = None) -> Turn:
        body = self._base_body(messages, max_tokens)
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        data, dt_ms = await self._post(body)
        msg = data["choices"][0]["message"]
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({"name": tc["function"]["name"], "args": args, "id": tc.get("id", "")})
        return Turn(text=msg.get("content"), tool_calls=tool_calls,
                    usage=data.get("usage", {}), latency_ms=dt_ms, raw=data)

    async def json(self, system: str, user: str, schema: dict,
                   schema_name: str = "result", max_tokens: Optional[int] = None) -> tuple[dict, Turn]:
        """Strict structured output -> parsed dict + the Turn (for timing)."""
        body = self._base_body(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens,
        )
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        }
        data, dt_ms = await self._post(body)
        msg = data["choices"][0]["message"]
        turn = Turn(text=msg.get("content"), tool_calls=[],
                    usage=data.get("usage", {}), latency_ms=dt_ms, raw=data)
        try:
            parsed = json.loads(msg.get("content") or "{}")
        except json.JSONDecodeError:
            parsed = {}
        return parsed, turn

    async def structured(self, system: str, user: str, schema: dict,
                         name: str = "result", max_tokens: Optional[int] = None) -> tuple[dict, Turn]:
        """Structured output via a forced tool call — the confirmed-reliable path on
        Cerebras (strict schemas must avoid minItems/maxItems). Returns (args, turn)."""
        tools = [{
            "type": "function",
            "function": {
                "name": name,
                "description": "Return the structured result.",
                "strict": True,
                "parameters": schema,
            },
        }]
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        turn = await self.chat(
            messages, tools=tools,
            tool_choice={"type": "function", "function": {"name": name}},
            max_tokens=max_tokens,
        )
        if turn.tool_calls:
            return turn.tool_calls[0]["args"], turn
        try:
            return json.loads(turn.text or "{}"), turn
        except json.JSONDecodeError:
            return {}, turn

    @staticmethod
    def image_message(text: str, data_uri: str, role: str = "user") -> dict:
        """Build a multimodal message with a base64 data-URI image (Cerebras only
        supports base64 data URIs, not hosted URLs)."""
        return {
            "role": role,
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }

    async def aclose(self) -> None:
        await self._client.aclose()
