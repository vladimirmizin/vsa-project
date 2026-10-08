"""Closing the loop: a paid Stripe checkout is attributed to the AI session that created the link."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from vsa_commerce.tracking.events import Event, EventType


def payment_event_from_stripe(payload: dict[str, Any], *, business_id: str) -> Event | None:
    """Map a ``checkout.session.completed`` webhook payload to an event.

    Returns None for other event types and for payments that did not start in an AI session.
    Signature verification belongs to the webhook endpoint, before this is called.
    """
    if payload.get("type") != "checkout.session.completed":
        return None
    session = payload.get("data", {}).get("object", {})
    reference = session.get("client_reference_id")
    if not reference:
        return None
    created = payload.get("created")
    return Event(
        at=datetime.fromtimestamp(created, UTC) if created else datetime.now(UTC),
        business_id=business_id,
        session_id=reference,
        channel="stripe",
        type=EventType.PAYMENT_COMPLETED,
        data={
            "amount_total": session.get("amount_total"),
            "currency": session.get("currency"),
            "stripe_session_id": session.get("id"),
            "payment_link": session.get("payment_link"),
        },
    )
