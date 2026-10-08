"""Client for any OpenAI-compatible chat API (DeepSeek by default)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"


class MissingApiKeyError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    temperature: float = 0.2

    @classmethod
    def from_env(cls, *, model: str | None = None, base_url: str | None = None) -> LLMSettings:
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise MissingApiKeyError("Set DEEPSEEK_API_KEY (or LLM_API_KEY) in the environment or in .env")
        return cls(
            api_key=api_key,
            base_url=base_url or os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL),
            model=model or os.environ.get("LLM_MODEL", DEFAULT_MODEL),
        )


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatTurn:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)

    def as_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ]
        return message


class OpenAICompatibleChat:
    def __init__(self, settings: LLMSettings, client: OpenAI | None = None) -> None:
        self.settings = settings
        self.client = client or OpenAI(api_key=settings.api_key, base_url=settings.base_url)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> ChatTurn:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature,
        }
        if tools:
            kwargs["tools"] = tools
        message = self.client.chat.completions.create(**kwargs).choices[0].message
        calls = [
            ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments or "{}")
            for c in message.tool_calls or []
            if getattr(c, "function", None) is not None
        ]
        return ChatTurn(content=message.content, tool_calls=calls)

    def complete_json(self, messages: list[dict[str, str]]) -> str:
        """Satisfies ``extraction.ChatModel`` so the same client powers catalog refresh."""
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        json.loads(content)  # fail here, not deep in validation, if the API ignored JSON mode
        return content
