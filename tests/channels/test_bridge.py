from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from vsa_commerce.channels.assistant import MAX_TOOL_ROUNDS, Assistant, system_prompt
from vsa_commerce.channels.bridge import McpBridge
from vsa_commerce.channels.llm import ChatTurn, ToolCall
from vsa_commerce.channels.mcp_server import build_server
from vsa_commerce.tracking import EventType

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


class ScriptedBackend:
    """Plays a model: each turn is either text or a list of (tool, arguments)."""

    def __init__(self, *turns: str | list[tuple[str, dict[str, Any]]]) -> None:
        self.turns = list(turns)
        self.requests: list[tuple[list[dict[str, Any]], list[dict[str, Any]] | None]] = []

    def complete(self, messages, tools=None) -> ChatTurn:
        self.requests.append((list(messages), tools))
        turn = self.turns.pop(0)
        if isinstance(turn, str):
            return ChatTurn(content=turn)
        calls = [ToolCall(id=f"call_{i}", name=n, arguments=json.dumps(a)) for i, (n, a) in enumerate(turn)]
        return ChatTurn(content=None, tool_calls=calls)


@pytest.fixture
def server(tools):
    return build_server(tools, channel="deepseek")


async def test_tools_are_translated_to_function_calling(server):
    async with McpBridge(server) as bridge:
        names = [t["function"]["name"] for t in bridge.tools]
        search = next(t for t in bridge.tools if t["function"]["name"] == "search_offerings")
    assert names == ["search_offerings", "get_offering_details", "check_availability", "create_checkout_link"]
    assert search["type"] == "function"
    assert search["function"]["parameters"]["required"] == ["query"]
    assert "VSA" in search["function"]["description"]


async def test_bridge_keeps_the_session_when_the_model_forgets_it(server, events):
    async with McpBridge(server) as bridge:
        await bridge.call("search_offerings", '{"query": "double axel"}')
        link = json.loads(await bridge.call("create_checkout_link", {"offering_id": "double-axel-club"}))
    sessions = {e.session_id for e in events.read()}
    assert sessions == {bridge.session_id}
    assert link["checkout_url"].endswith(f"client_reference_id={bridge.session_id}")
    assert {e.channel for e in events.read()} == {"deepseek"}


async def test_errors_are_returned_to_the_model(server):
    async with McpBridge(server) as bridge:
        bad_json = await bridge.call("search_offerings", "{not json")
        unknown = await bridge.call("get_offering_details", {"offering_id": "quad-club"})
    assert bad_json.startswith("ERROR: arguments are not valid JSON")
    assert unknown.startswith("ERROR:")
    assert "Valid ids" in unknown


async def test_sales_flow_over_three_user_turns(server, events):
    backend = ScriptedBackend(
        [("search_offerings", {"query": "improve my double axel", "max_price": 350})],
        [("get_offering_details", {"offering_id": "double-axel-club"})],
        "The 6-Month Double Axel Club fits: $299 every 6 months...",
        [("check_availability", {"offering_id": "double-axel-club", "date": "2026-11-06"})],
        "Yes, you can start on Saturday 7 November.",
        [("create_checkout_link", {"offering_id": "double-axel-club"})],
        "Here is your checkout link.",
    )
    async with McpBridge(server) as bridge:
        assistant = Assistant(backend, bridge, instructions=server.instructions, now=NOW)
        first = await assistant.send("I want to improve my Double Axel, online, under $350.")
        second = await assistant.send("I'm free on November 6. Can I join?")
        third = await assistant.send("I want to join.")

    assert [t.name for t in first.tools_used] == ["search_offerings", "get_offering_details"]
    assert [t.name for t in second.tools_used] == ["check_availability"]
    assert [t.name for t in third.tools_used] == ["create_checkout_link"]
    assert third.text == "Here is your checkout link."

    tool_messages = [m for m in assistant.messages if m["role"] == "tool"]
    assert len(tool_messages) == 4
    checkout = json.loads(tool_messages[-1]["content"])
    assert checkout["checkout_url"].startswith("https://buy.stripe.com/14AeVd6anbti69kcJ9dMM1M?client_reference_id=")

    recorded = events.read()
    assert [e.type for e in recorded] == [
        EventType.SEARCH,
        EventType.OFFERING_VIEWED,
        EventType.AVAILABILITY_CHECKED,
        EventType.CHECKOUT_CREATED,
    ]
    assert len({e.session_id for e in recorded}) == 1


async def test_assistant_messages_follow_the_openai_format(server):
    backend = ScriptedBackend([("search_offerings", {"query": "double axel"})], "done")
    async with McpBridge(server) as bridge:
        assistant = Assistant(backend, bridge, instructions="be helpful", now=NOW)
        await assistant.send("hi")
    call_message = assistant.messages[2]
    assert call_message["role"] == "assistant"
    assert call_message["tool_calls"][0]["function"]["name"] == "search_offerings"
    assert assistant.messages[3] == {
        "role": "tool",
        "tool_call_id": "call_0",
        "content": assistant.messages[3]["content"],
    }


async def test_gives_up_after_too_many_rounds(server):
    loop = [("search_offerings", {"query": "double axel"})]
    backend = ScriptedBackend(*([loop] * MAX_TOOL_ROUNDS))
    async with McpBridge(server) as bridge:
        reply = await Assistant(backend, bridge, instructions=None, now=NOW).send("hi")
    assert reply.text.startswith("Sorry")
    assert len(reply.tools_used) == MAX_TOOL_ROUNDS


async def test_baseline_mode_sends_no_tools():
    backend = ScriptedBackend("I am not sure VSA has such a program.")
    reply = await Assistant(backend, None, instructions=None, now=NOW).send("Does VSA have a Double Axel program?")
    assert reply.text.startswith("I am not sure")
    assert backend.requests[0][1] is None


def test_system_prompt_carries_today():
    assert system_prompt(None, NOW) == "Today is Thursday, 08 October 2026."
    assert system_prompt("Rules.", NOW).startswith("Rules.\n\nToday is Thursday")
