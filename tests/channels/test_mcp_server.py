from __future__ import annotations

import pytest
from fastmcp import Client

from vsa_commerce.channels.mcp_server import build_server
from vsa_commerce.tracking import EventType

TOOLS = {"search_offerings", "get_offering_details", "check_availability", "create_checkout_link"}


@pytest.fixture
def server(tools):
    return build_server(tools)


async def test_exposes_four_tools_with_schemas(server):
    async with Client(server) as client:
        listed = {t.name: t for t in await client.list_tools()}
    assert set(listed) == TOOLS
    search = listed["search_offerings"]
    assert search.input_schema["required"] == ["query"]
    assert set(search.input_schema["properties"]) == {"query", "max_price", "session_id"}
    assert "Victory Skating / VSA" in search.description
    assert listed["check_availability"].annotations.read_only_hint is True
    assert listed["create_checkout_link"].annotations.read_only_hint is False


def test_instructions_name_both_brands(server):
    assert "Victory Skating Academy (also known as Victory Skating / VSA" in (server.instructions or "")


async def test_full_sales_flow_in_one_session(server, events):
    async with Client(server) as client:
        found = await client.call_tool(
            "search_offerings", {"query": "improve my Double Axel, online, under $350", "max_price": 350}
        )
        offering_id = found.structured_content["results"][0]["offering_id"]
        session = found.structured_content["session_id"]
        await client.call_tool("get_offering_details", {"offering_id": offering_id, "session_id": session})
        available = await client.call_tool(
            "check_availability", {"offering_id": offering_id, "date": "2026-11-06", "session_id": session}
        )
        link = await client.call_tool("create_checkout_link", {"offering_id": offering_id, "session_id": session})

    assert offering_id == "double-axel-club"
    assert available.structured_content["availability"]["can_join"] is True
    url = link.structured_content["checkout_url"]
    assert url.startswith("https://buy.stripe.com/14AeVd6anbti69kcJ9dMM1M?client_reference_id=")

    recorded = events.read()
    assert [e.type for e in recorded] == [
        EventType.SEARCH,
        EventType.OFFERING_VIEWED,
        EventType.AVAILABILITY_CHECKED,
        EventType.CHECKOUT_CREATED,
    ]
    assert {e.session_id for e in recorded} == {session}
    assert url.endswith(f"client_reference_id={session}")
    assert {e.channel for e in recorded} == {"mcp"}


async def test_separate_clients_are_separate_sessions(server, events):
    for _ in range(2):
        async with Client(server) as client:
            await client.call_tool("search_offerings", {"query": "double axel"})
    assert len({e.session_id for e in events.read()}) == 2


async def test_bad_input_comes_back_as_a_tool_error(server):
    async with Client(server) as client:
        result = await client.call_tool("check_availability", {"offering_id": "quad-club"}, raise_on_error=False)
    assert result.is_error
    assert "Valid ids:" in result.content[0].text


async def test_calls_without_session_id_start_new_sessions(server, events):
    async with Client(server) as client:
        await client.call_tool("search_offerings", {"query": "double axel"})
        await client.call_tool("search_offerings", {"query": "double axel", "session_id": "bad id!"})
    assert len({e.session_id for e in events.read()}) == 2


@pytest.mark.parametrize(
    ("given", "kept"), [("abc12345", True), ("short", False), ("has space 123", False), (None, False)]
)
def test_resolve_session(given, kept):
    from vsa_commerce.channels.mcp_server import resolve_session

    assert (resolve_session(given) == given) is kept
