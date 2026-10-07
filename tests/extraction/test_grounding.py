from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from vsa_commerce.extraction import ExtractedOffering, check_grounding
from vsa_commerce.extraction.grounding import amount_in_text


def _problems(request, answer) -> list[str]:
    return check_grounding(ExtractedOffering.model_validate(answer), request)


def test_correct_answer_is_grounded(axel_request, good_answer):
    assert _problems(axel_request, good_answer) == []


def test_list_price_must_appear(axel_request, good_answer):
    bad = copy.deepcopy(good_answer)
    bad["offers"][0]["list_price"]["amount"] = "799.00"
    assert any("list_price 799.00 does not appear" in p for p in _problems(axel_request, bad))


def test_checkout_url_must_be_on_the_page(axel_request, good_answer):
    bad = copy.deepcopy(good_answer)
    bad["offers"][0]["checkout_url"] = "https://buy.stripe.com/fake"
    assert any("is not a link on the page" in p for p in _problems(axel_request, bad))


def test_payment_link_must_be_chosen_when_ambiguous(axel_request, good_answer):
    bad = copy.deepcopy(good_answer)
    bad["offers"][0]["checkout_url"] = None
    two_links = axel_request.model_copy(
        update={"payment_links": ["https://buy.stripe.com/a", "https://buy.stripe.com/b"]}
    )
    assert any("choose checkout_url" in p for p in _problems(two_links, bad))


def test_single_payment_link_may_be_left_implicit(axel_request, good_answer):
    answer = copy.deepcopy(good_answer)
    answer["offers"][0]["checkout_url"] = None
    assert _problems(axel_request, answer) == []


def test_coach_must_be_named_on_the_page(axel_request, good_answer):
    bad = copy.deepcopy(good_answer)
    bad["staff"][0]["name"] = "Coach Helena"
    assert any("'Coach Helena' is not named" in p for p in _problems(axel_request, bad))


def test_related_offering_must_be_known(axel_request, good_answer):
    bad = good_answer | {"related": [{"offering_id": "quad-jumps-club", "relation": "next_step"}]}
    assert any("quad-jumps-club" in p for p in _problems(axel_request, bad))


def test_cannot_relate_to_itself(axel_request, good_answer):
    bad = good_answer | {"related": [{"offering_id": "double-axel-club", "relation": "next_step"}]}
    assert _problems(axel_request, bad)


def test_platform_must_be_mentioned(axel_request, good_answer):
    assert any("'Zoom'" in p for p in _problems(axel_request, good_answer | {"platform": "Zoom"}))


@pytest.mark.parametrize(
    ("amount", "text", "found"),
    [
        ("299", "for just $299/6 months", True),
        ("299.00", "$299.00", True),
        ("29", "for just $299", False),
        ("99", "$299", False),
        ("1299", "$1,299 per year", True),
        ("6.23", "$6 / class", False),
    ],
)
def test_amount_in_text(amount, text, found):
    assert amount_in_text(Decimal(amount), text) is found
