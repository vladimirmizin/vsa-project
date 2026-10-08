"""MCP server: the single interface assistants use. Other channels reuse its tool definitions."""

from __future__ import annotations

import argparse
import logging
import re
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from vsa_commerce.catalog.store import CatalogStore, default_data_dir
from vsa_commerce.errors import ToolInputError
from vsa_commerce.tools import CallContext, CommerceTools
from vsa_commerce.tools.views import AvailabilityView, CheckoutLink, OfferingDetails, SearchResponse
from vsa_commerce.tracking import JsonlEventLog

T = TypeVar("T")

INSTRUCTIONS = """\
You help customers of {business} (also known as {brands}) find the right offering and enroll.

- Answer only from tool results. Never guess prices, schedules, coaches or links.
- Start with search_offerings whenever the customer describes a goal, level or budget, or asks
  whether {brands} has something. Then use get_offering_details before describing an offering.
- For any question about dates or starting, call check_availability. A start date printed on the
  website is not a deadline for programs that run every week.
- When the customer wants to join, call create_checkout_link. Before sharing the link, state the
  price and billing terms it returns (renewal, cancellation, refunds) in plain words.
- Every result has a session_id. Pass it to every later call in the same conversation.
- Ask for the customer's timezone when local class times matter.
- If nothing fits, say so honestly.
"""

READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}

OfferingId = Annotated[str, Field(description="Offering id from search_offerings, e.g. 'double-axel-club'.")]
SessionId = Annotated[
    str | None,
    Field(description="session_id from an earlier result in this conversation. Omit only on the first call."),
]
CustomerTimezone = Annotated[
    str | None,
    Field(description="Customer's IANA timezone if known, e.g. 'Europe/London', to show local class times."),
]


def build_server(tools: CommerceTools, *, channel: str = "mcp") -> FastMCP:
    business = tools.catalog.business
    brands = " / ".join(business.brand_names)
    mcp = FastMCP(
        name=f"{business.name} commerce",
        instructions=INSTRUCTIONS.format(business=business.name, brands=brands),
    )

    def call(session_id: str | None, fn: Callable[[CallContext], T]) -> T:
        try:
            return fn(CallContext(session_id=resolve_session(session_id), channel=channel))
        except ToolInputError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        annotations=READ_ONLY,
        description=(
            f"Find what {business.name} ({brands}) offers for the customer's request. Use it first when the "
            "customer describes a goal, a skill level or a budget, or asks whether the business has something, "
            "even if they name only one of the brands. Returns ranked matches with prices and why each matches."
        ),
    )
    def search_offerings(
        query: Annotated[
            str, Field(description="The customer's request in their own words, e.g. 'improve my double axel'.")
        ],
        max_price: Annotated[
            float | None, Field(description="Budget ceiling in USD as a number, only if the customer gave one.")
        ] = None,
        session_id: SessionId = None,
    ) -> SearchResponse:
        return call(session_id, lambda c: tools.search_offerings(c, query, max_price))

    @mcp.tool(
        annotations=READ_ONLY,
        description=(
            "Full facts about one offering: what it is, level and prerequisites, coach, weekly schedule with local "
            "times, number of classes, what is included, required equipment, price and billing terms. Call it before "
            "describing an offering and quote prices and terms only from its result."
        ),
    )
    def get_offering_details(
        offering_id: OfferingId, timezone: CustomerTimezone = None, session_id: SessionId = None
    ) -> OfferingDetails:
        return call(session_id, lambda c: tools.get_offering_details(c, offering_id, timezone))

    @mcp.tool(
        annotations=READ_ONLY,
        description=(
            "Check whether the customer can start around a date and list the next sessions in their timezone. "
            "Programs that run every week can be joined at any time; a start date shown on the website is not a "
            "deadline, so use this tool instead of answering from page text."
        ),
    )
    def check_availability(
        offering_id: OfferingId,
        date: Annotated[
            str | None,
            Field(description="Date the customer mentioned, as YYYY-MM-DD. Resolve relative dates before calling."),
        ] = None,
        timezone: CustomerTimezone = None,
        session_id: SessionId = None,
    ) -> AvailabilityView:
        return call(session_id, lambda c: tools.check_availability(c, offering_id, date, timezone))

    @mcp.tool(
        annotations={"readOnlyHint": False, "openWorldHint": False},
        description=(
            "Create the link where the customer completes enrollment and payment. Call it only after the customer "
            "says they want to join or buy. Before sharing the link, tell them the price and the billing terms it "
            "returns (renewal, cancellation, refunds)."
        ),
    )
    def create_checkout_link(
        offering_id: OfferingId,
        *,
        offer_id: Annotated[
            str | None, Field(description="Specific offer id from the offering's prices; omit for the main offer.")
        ] = None,
        email: Annotated[
            str | None, Field(description="Customer's email, only if they gave it, to prefill the checkout.")
        ] = None,
        timezone: CustomerTimezone = None,
        date: Annotated[
            str | None,
            Field(description="Date the customer wants to start, as YYYY-MM-DD, if they mentioned one."),
        ] = None,
        session_id: SessionId = None,
    ) -> CheckoutLink:
        return call(
            session_id,
            lambda c: tools.create_checkout_link(
                c, offering_id, offer_id=offer_id, email=email, timezone=timezone, date=date
            ),
        )

    return mcp


_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def resolve_session(session_id: str | None) -> str:
    """MCP 2026-07-28 is stateless, so the conversation is carried by an id the model passes back."""
    if session_id and _SESSION_ID.match(session_id):
        return session_id
    return uuid.uuid4().hex


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the commerce MCP server for one business.")
    parser.add_argument("--business", default="victory-skating")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--events", type=Path, default=Path("var/events.jsonl"))
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    # stdout carries the MCP protocol in stdio mode, so logs go to stderr
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    store = CatalogStore(args.data_dir or default_data_dir())
    tools = CommerceTools(store, args.business, events=JsonlEventLog(args.events))
    server = build_server(tools)
    if args.transport == "http":
        server.run(transport="http", port=args.port, show_banner=False)
    else:
        server.run(show_banner=False)


if __name__ == "__main__":
    main()
