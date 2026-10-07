"""Checks that an extraction is supported by the page: prices, people, links, platform."""

from __future__ import annotations

import re
from decimal import Decimal

from vsa_commerce.domain.models import CheckoutMethod
from vsa_commerce.extraction.schema import ExtractedOffering, ExtractionRequest

_TITLE_PREFIX = re.compile(r"^(?:top\s+)?(?:coach|stylist|instructor|teacher|trainer)\s+", re.IGNORECASE)


def amount_in_text(amount: Decimal, text: str) -> bool:
    variants = {f"{amount:.2f}"}
    if amount == amount.to_integral_value():
        whole = int(amount)
        variants |= {str(whole), f"{whole:,}"}
    return any(re.search(rf"(?<![\d.,]){re.escape(v)}(?!\d)", text) for v in variants)


def check_grounding(extracted: ExtractedOffering, request: ExtractionRequest) -> list[str]:
    text = request.page_text
    lowered = text.lower()
    problems: list[str] = []

    for offer in extracted.offers:
        for label, money in (("price", offer.price), ("list_price", offer.list_price)):
            if money is not None and not amount_in_text(money.amount, text):
                problems.append(f"offer {offer.id!r}: {label} {money.amount} does not appear on the page")
        if offer.checkout_url is not None and offer.checkout_url not in request.payment_links:
            problems.append(f"offer {offer.id!r}: checkout_url {offer.checkout_url!r} is not a link on the page")
        ambiguous = offer.checkout_url is None and len(request.payment_links) != 1
        if offer.checkout_method is CheckoutMethod.PAYMENT_LINK and ambiguous:
            problems.append(f"offer {offer.id!r}: choose checkout_url from the payment links")

    for person in extracted.staff:
        if _TITLE_PREFIX.sub("", person.name).lower() not in lowered:
            problems.append(f"staff member {person.name!r} is not named on the page")

    allowed = set(request.other_offering_ids)
    for rel in extracted.related:
        if rel.offering_id not in allowed:
            problems.append(f"related offering {rel.offering_id!r} is not one of {sorted(allowed)}")

    if extracted.platform and extracted.platform.lower() not in lowered:
        problems.append(f"platform {extracted.platform!r} is not mentioned on the page")

    return problems
