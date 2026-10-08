from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tests.support.paths import DATA_DIR, ROOT
from vsa_commerce.channels import chat_cli
from vsa_commerce.channels.assistant import Reply, ToolTrace
from vsa_commerce.channels.llm import ChatTurn, ToolCall


def test_read_script(tmp_path):
    script = tmp_path / "s.txt"
    script.write_text("# comment\nfirst\n\n\nsecond a\nsecond b\n\n", encoding="utf-8")
    assert chat_cli.read_script(script) == [["first"], ["second a", "second b"]]


def test_demo_script_has_the_assignment_queries():
    conversations = chat_cli.read_script(ROOT / "demo" / "assignment.txt")
    assert len(conversations) == 7
    assert conversations[-1][-1] == "I want to join."


def test_format_call_hides_the_session():
    assert chat_cli.format_call("t", {"offering_id": "x", "session_id": "s"}) == 't(offering_id="x")'


def test_transcript(tmp_path):
    transcript = chat_cli.Transcript("title")
    transcript.turn("hi", Reply("hello", [ToolTrace("search_offerings", {"query": "x"}, ok=False)]))
    text = transcript.save(tmp_path, "tools").read_text(encoding="utf-8")
    assert "**User:** hi" in text
    assert '> tool: `search_offerings(query="x")` (error)' in text


def _args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "business": "victory-skating",
        "data_dir": DATA_DIR,
        "events": tmp_path / "events.jsonl",
        "channel": "deepseek",
        "model": None,
        "base_url": None,
        "no_tools": False,
        "script": ROOT / "demo" / "assignment.txt",
        "save": tmp_path / "transcripts",
    }
    return argparse.Namespace(**(values | overrides))


async def test_missing_key_exits_with_a_message(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert await chat_cli.run(_args(tmp_path)) == 2
    assert "DEEPSEEK_API_KEY" in capsys.readouterr().err


@pytest.mark.parametrize("no_tools", [False, True])
async def test_script_run_end_to_end(monkeypatch, tmp_path, capsys, no_tools):
    class FakeChat:
        def __init__(self, settings) -> None:
            self.calls = 0

        def complete(self, messages, tools=None):
            self.calls += 1
            if tools and messages[-1]["role"] == "user":
                return ChatTurn(None, [ToolCall("c", "search_offerings", '{"query": "double axel"}')])
            return ChatTurn("answer")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(chat_cli, "OpenAICompatibleChat", FakeChat)
    assert await chat_cli.run(_args(tmp_path, no_tools=no_tools)) == 0

    out = capsys.readouterr().out
    assert out.count("Assistant: answer") == 9
    assert ("-> search_offerings" in out) is not no_tools
    saved = list((tmp_path / "transcripts").glob("*.md"))
    assert len(saved) == 1
    assert saved[0].name.endswith("baseline.md" if no_tools else "tools.md")
