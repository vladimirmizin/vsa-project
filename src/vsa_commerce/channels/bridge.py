"""Exposes an MCP server's tools to a function-calling model; tool definitions come from the server itself."""

from __future__ import annotations

import json
from types import TracebackType
from typing import Any, Self

from fastmcp import Client, FastMCP

SESSION_ARG = "session_id"


class McpBridge:
    def __init__(self, server: FastMCP | Any) -> None:
        self._client: Client[Any] = Client(server)
        self.session_id: str | None = None
        self._tools: list[dict[str, Any]] = []

    async def __aenter__(self) -> Self:
        await self._client.__aenter__()  # type: ignore[no-untyped-call]
        self._tools = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description or "", "parameters": t.input_schema},
            }
            for t in await self._client.list_tools()
        ]
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self._client.__aexit__(exc_type, exc, tb)  # type: ignore[no-untyped-call]

    @property
    def tools(self) -> list[dict[str, Any]]:
        return self._tools

    async def call(self, name: str, arguments: str | dict[str, Any]) -> str:
        """Run a tool and return its result as text for the model. Errors are returned, not raised."""
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        except json.JSONDecodeError as exc:
            return f"ERROR: arguments are not valid JSON ({exc}). Call the tool again with a JSON object."
        if self.session_id and self._accepts_session(name):
            # the bridge owns the conversation, so it keeps the session even if the model forgets it
            args[SESSION_ARG] = self.session_id

        result = await self._client.call_tool(name, args, raise_on_error=False)
        if result.is_error:
            text = " ".join(getattr(block, "text", "") for block in result.content).strip()
            return f"ERROR: {text or 'tool failed'}"
        payload = result.structured_content or {}
        if isinstance(payload.get(SESSION_ARG), str):
            self.session_id = payload[SESSION_ARG]
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _accepts_session(self, name: str) -> bool:
        for tool in self._tools:
            if tool["function"]["name"] == name:
                return SESSION_ARG in tool["function"]["parameters"].get("properties", {})
        return False
