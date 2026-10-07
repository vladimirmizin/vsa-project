from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

from vsa_commerce.domain.models import ADVERTISED_START_KEY
from vsa_commerce.extraction import ExtractedOffering, ExtractionRequest

OfferingEdit = Callable[[str, dict[str, Any]], None]


def extracted_from_snapshot(offering: dict[str, Any]) -> ExtractedOffering:
    """The answer a perfect extractor would give, rebuilt from a stored offering."""
    data = copy.deepcopy(offering)
    provenance = data.pop("provenance")
    del data["id"], data["business_id"]
    offers = []
    for offer in data.pop("offers"):
        checkout = offer.pop("checkout")
        offers.append(
            {
                **offer,
                "checkout_method": checkout["method"],
                "checkout_url": checkout.get("url"),
                "checkout_label": checkout.get("label"),
            }
        )
    advertised = {k: v for k, v in provenance.get("advertised", {}).items() if k != ADVERTISED_START_KEY}
    return ExtractedOffering.model_validate(
        {**data, "offers": offers, "advertised": advertised, "conflicts": provenance.get("conflicts", [])}
    )


class SnapshotExtractor:
    def __init__(self, snapshot: dict[str, Any], edit: OfferingEdit | None = None) -> None:
        self.by_id = {o["id"]: o for o in snapshot["offerings"]}
        self.edit = edit
        self.requests: list[ExtractionRequest] = []

    def extract(self, request: ExtractionRequest) -> ExtractedOffering:
        self.requests.append(request)
        offering = copy.deepcopy(self.by_id[request.offering_id])
        if self.edit:
            self.edit(request.offering_id, offering)
        return extracted_from_snapshot(offering)


class ScriptedChat:
    def __init__(self, *answers: str | dict[str, Any]) -> None:
        self.answers = [a if isinstance(a, str) else json.dumps(a) for a in answers]
        self.calls: list[list[dict[str, str]]] = []

    def complete_json(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(copy.deepcopy(messages))
        return self.answers.pop(0)
