from __future__ import annotations

from types import SimpleNamespace

import pytest

from vsa_commerce.channels.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    ChatTurn,
    LLMSettings,
    MissingApiKeyError,
    OpenAICompatibleChat,
    ToolCall,
)


class FakeCompletions:
    def __init__(self, message) -> None:
        self.message = message
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=self.message)])


def _chat(message) -> tuple[OpenAICompatibleChat, FakeCompletions]:
    completions = FakeCompletions(message)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAICompatibleChat(LLMSettings(api_key="k"), client=client), completions


def test_tool_calls_are_parsed():
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="search_offerings", arguments='{"query":"x"}'))
    chat, completions = _chat(SimpleNamespace(content=None, tool_calls=[call]))
    turn = chat.complete([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    assert turn.tool_calls == [ToolCall(id="c1", name="search_offerings", arguments='{"query":"x"}')]
    assert completions.kwargs["model"] == DEFAULT_MODEL
    assert completions.kwargs["tools"] == [{"type": "function"}]


def test_plain_answer_sends_no_tools():
    chat, completions = _chat(SimpleNamespace(content="Hello", tool_calls=None))
    assert chat.complete([{"role": "user", "content": "hi"}]).content == "Hello"
    assert "tools" not in completions.kwargs


def test_json_mode_for_extraction():
    chat, completions = _chat(SimpleNamespace(content='{"name": "x"}', tool_calls=None))
    assert chat.complete_json([{"role": "user", "content": "extract"}]) == '{"name": "x"}'
    assert completions.kwargs["response_format"] == {"type": "json_object"}
    assert completions.kwargs["temperature"] == 0


def test_json_mode_rejects_non_json():
    chat, _ = _chat(SimpleNamespace(content="Sure!", tool_calls=None))
    with pytest.raises(ValueError, match="Expecting value"):
        chat.complete_json([{"role": "user", "content": "extract"}])


def test_turn_as_message():
    turn = ChatTurn(content=None, tool_calls=[ToolCall(id="c1", name="t", arguments="{}")])
    assert turn.as_message() == {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{}"}}],
    }
    assert ChatTurn(content="hi").as_message() == {"role": "assistant", "content": "hi"}


class TestSettings:
    def test_deepseek_defaults(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        settings = LLMSettings.from_env()
        assert (settings.api_key, settings.base_url, settings.model) == ("sk-test", DEFAULT_BASE_URL, DEFAULT_MODEL)

    def test_any_openai_compatible_provider(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "other")
        monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        settings = LLMSettings.from_env(model="some/model")
        assert (settings.api_key, settings.base_url, settings.model) == (
            "other",
            "https://openrouter.ai/api/v1",
            "some/model",
        )

    def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(MissingApiKeyError):
            LLMSettings.from_env()
