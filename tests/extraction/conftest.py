from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from tests.support.fakes import extracted_from_snapshot
from tests.support.paths import tilda_html
from vsa_commerce.connectors.tilda import parse_tilda_page
from vsa_commerce.extraction import ExtractionRequest


@pytest.fixture
def axel_request() -> ExtractionRequest:
    page = parse_tilda_page(tilda_html("doubleaxel"))
    return ExtractionRequest(
        business_id="victory-skating",
        offering_id="double-axel-club",
        source_url="https://victoryskating.com/doubleaxel",
        fetched_on=date(2026, 10, 7),
        page_title=page.title,
        page_text=page.text,
        payment_links=page.payment_links,
        known_offering_ids=["double-jumps-club", "double-axel-club", "triple-jumps-club"],
    )


@pytest.fixture
def good_answer(vsa_source_data) -> dict[str, Any]:
    offering = next(o for o in vsa_source_data["offerings"] if o["id"] == "double-axel-club")
    answer = extracted_from_snapshot(offering).model_dump(mode="json")
    # private lessons are not one of the page offerings
    answer["related"] = [r for r in answer["related"] if r["offering_id"] != "private-lesson-marta"]
    return answer
