"""One server implementation, many businesses: each tenant gets its own catalog, tool texts and events."""

from __future__ import annotations

from fastmcp import Client

from vsa_commerce.channels.mcp_server import build_server
from vsa_commerce.tools import CommerceTools
from vsa_commerce.tracking import InMemoryEventLog


async def test_same_server_code_serves_a_shopify_store(store, now):
    events = InMemoryEventLog()
    shop = build_server(CommerceTools(store, "edge-skate-shop", events=events, clock=lambda: now))
    async with Client(shop) as client:
        found = await client.call_tool("search_offerings", {"query": "off-ice spinner for rotation practice"})
        result = found.structured_content["results"][0]
        link = await client.call_tool(
            "create_checkout_link",
            {"offering_id": result["offering_id"], "session_id": found.structured_content["session_id"]},
        )
    assert result["offering_id"] == "off-ice-spinner-board"
    assert found.structured_content["brand_names"] == ["Edge", "Edge Skate Shop"]
    excluded = {e["offering_id"]: e["reason"] for e in found.structured_content["excluded"]}
    assert excluded == {"blade-guard-set": "sold out"}
    url = link.structured_content["checkout_url"]
    assert url.startswith("https://edge-skate.example.com/cart/4401:1?attributes%5Bai_session%5D=")
    assert link.structured_content["first_session"] is None
    assert {e.business_id for e in events.read()} == {"edge-skate-shop"}


def test_tool_texts_follow_the_tenant(store, now):
    shop = build_server(CommerceTools(store, "edge-skate-shop", events=InMemoryEventLog(), clock=lambda: now))
    skating = build_server(CommerceTools(store, "victory-skating", events=InMemoryEventLog(), clock=lambda: now))
    assert "Edge / Edge Skate Shop" in (shop.instructions or "")
    assert "Victory Skating / VSA" in (skating.instructions or "")
    assert "Victory" not in (shop.instructions or "")
