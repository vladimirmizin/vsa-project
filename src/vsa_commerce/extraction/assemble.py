from __future__ import annotations

from datetime import datetime
from typing import Any

from vsa_commerce.domain.models import CheckoutMethod
from vsa_commerce.extraction.schema import ExtractedOffer, ExtractedOffering, ExtractionRequest

_REFERENCE_PARAMS = {
    "buy.stripe.com": "client_reference_id",
}


def reference_param_for(url: str | None) -> str | None:
    if not url:
        return None
    return next((param for host, param in _REFERENCE_PARAMS.items() if f"//{host}/" in url), None)


def assemble_offering(
    extracted: ExtractedOffering,
    request: ExtractionRequest,
    *,
    platform: str,
    fetched_at: datetime,
) -> dict[str, Any]:
    content = extracted.model_dump(mode="json", exclude={"offers", "advertised", "conflicts"})
    return {
        "id": request.offering_id,
        "business_id": request.business_id,
        **content,
        "offers": [_assemble_offer(offer, request.payment_links) for offer in extracted.offers],
        "provenance": {
            "source_url": request.source_url,
            "platform": platform,
            "fetched_at": fetched_at.isoformat(),
            "advertised": extracted.advertised,
            "conflicts": extracted.conflicts,
        },
    }


def _assemble_offer(offer: ExtractedOffer, payment_links: list[str]) -> dict[str, Any]:
    url = offer.checkout_url
    if url is None and offer.checkout_method is CheckoutMethod.PAYMENT_LINK and len(payment_links) == 1:
        url = payment_links[0]
    data = offer.model_dump(mode="json", exclude={"checkout_method", "checkout_url", "checkout_label"})
    data["checkout"] = {
        "method": offer.checkout_method.value,
        "url": url,
        "label": offer.checkout_label,
        "reference_param": reference_param_for(url),
    }
    return data
