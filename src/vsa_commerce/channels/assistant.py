"""A conversation with a function-calling model over the MCP tools."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from vsa_commerce.channels.bridge import McpBridge
from vsa_commerce.channels.llm import ChatTurn

MAX_TOOL_ROUNDS = 8


class ChatBackend(Protocol):
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> ChatTurn: ...


@dataclass(frozen=True)
class ToolTrace:
    name: str
    arguments: dict[str, Any]
    ok: bool


@dataclass
class Reply:
    text: str
    tools_used: list[ToolTrace] = field(default_factory=list)


def system_prompt(instructions: str | None, now: datetime) -> str:
    today = f"Today is {now:%A, %d %B %Y}."
    return f"{instructions.strip()}\n\n{today}" if instructions else today


class Assistant:
    def __init__(
        self, backend: ChatBackend, bridge: McpBridge | None, *, instructions: str | None, now: datetime
    ) -> None:
        self.backend = backend
        self.bridge = bridge
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(instructions, now)}]

    async def send(self, text: str) -> Reply:
        self.messages.append({"role": "user", "content": text})
        tools = self.bridge.tools if self.bridge else None
        trace: list[ToolTrace] = []

        for _ in range(MAX_TOOL_ROUNDS):
            turn = await asyncio.to_thread(self.backend.complete, self.messages, tools)
            self.messages.append(turn.as_message())
            if not turn.tool_calls or self.bridge is None:
                return Reply(text=turn.content or "", tools_used=trace)
            for call in turn.tool_calls:
                result = await self.bridge.call(call.name, call.arguments)
                trace.append(ToolTrace(call.name, _safe_json(call.arguments), not result.startswith("ERROR:")))
                self.messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

        return Reply(text="Sorry, I could not complete that request.", tools_used=trace)


def _safe_json(arguments: str) -> dict[str, Any]:
    try:
        value = json.loads(arguments)
    except json.JSONDecodeError:
        return {"raw": arguments}
    return value if isinstance(value, dict) else {"value": value}
