"""Versioned JSON feed of a catalog, with the derived values a consumer would otherwise recompute."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from vsa_commerce.domain.models import Catalog

FEED_VERSION = "1"


def render_feed(catalog: Catalog, *, now: datetime) -> dict[str, Any]:
    data = catalog.model_dump(mode="json")
    for offering, raw in zip(catalog.offerings, data["offerings"], strict=True):
        for offer, raw_offer in zip(offering.offers, raw["offers"], strict=True):
            per_session = offer.price_per_session
            raw_offer["price_per_session"] = per_session.model_dump(mode="json") if per_session else None
            raw_offer["discount_percent"] = offer.discount_percent
    return {"version": FEED_VERSION, "generated_at": now.isoformat(), **data}
