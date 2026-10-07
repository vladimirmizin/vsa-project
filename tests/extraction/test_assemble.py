from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest

from vsa_commerce.extraction import ExtractedOffering, assemble_offering
from vsa_commerce.extraction.assemble import reference_param_for

FETCHED_AT = datetime(2026, 10, 8, tzinfo=UTC)


def _assemble(request, answer) -> dict:
    return assemble_offering(ExtractedOffering.model_validate(answer), request, platform="tilda", fetched_at=FETCHED_AT)


def test_identity_and_provenance_come_from_the_connector(axel_request, good_answer):
    offering = _assemble(axel_request, good_answer)
    assert offering["id"] == "double-axel-club"
    assert offering["business_id"] == "victory-skating"
    assert offering["provenance"]["source_url"] == "https://victoryskating.com/doubleaxel"
    assert offering["provenance"]["fetched_at"] == "2026-10-08T00:00:00+00:00"


def test_single_payment_link_is_filled_in(axel_request, good_answer):
    answer = copy.deepcopy(good_answer)
    answer["offers"][0]["checkout_url"] = None
    assert _assemble(axel_request, answer)["offers"][0]["checkout"] == {
        "method": "payment_link",
        "url": "https://buy.stripe.com/14AeVd6anbti69kcJ9dMM1M",
        "label": "Register Now",
        "reference_param": "client_reference_id",
    }


@pytest.mark.parametrize(
    ("url", "param"),
    [
        ("https://buy.stripe.com/14AeVd6anbti69kcJ9dMM1M", "client_reference_id"),
        ("https://www.paypal.com/checkout/abc", None),
        (None, None),
    ],
)
def test_reference_param_by_checkout_host(url, param):
    assert reference_param_for(url) == param
