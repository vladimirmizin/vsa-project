from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from tests.support.fakes import ScriptedChat
from vsa_commerce.errors import ExtractionError
from vsa_commerce.extraction import LLMOfferingExtractor


def _feedback(chat: ScriptedChat, attempt: int = 1) -> str:
    return chat.calls[attempt][-1]["content"]


def test_valid_answer_accepted_first_time(axel_request, good_answer):
    chat = ScriptedChat(good_answer)
    assert LLMOfferingExtractor(chat).extract(axel_request).name == "6-Month Double Axel Club"
    assert len(chat.calls) == 1


def test_prompt_contains_rules_schema_and_page(axel_request, good_answer):
    chat = ScriptedChat(good_answer)
    LLMOfferingExtractor(chat).extract(axel_request)
    system, user = chat.calls[0]
    assert "Never invent" in system["content"]
    assert "on or after 2026-10-07" in system["content"]
    assert "double-jumps-club, triple-jumps-club" in system["content"]
    assert '"ExtractedOffer"' in system["content"]
    assert "https://buy.stripe.com/14AeVd6anbti69kcJ9dMM1M" in user["content"]
    assert "48 Live Group Classes" in user["content"]


def test_invented_price_is_sent_back_and_corrected(axel_request, good_answer):
    bad = copy.deepcopy(good_answer)
    bad["offers"][0]["price"]["amount"] = "249.00"
    chat = ScriptedChat(bad, good_answer)
    assert LLMOfferingExtractor(chat).extract(axel_request).offers[0].price.amount == Decimal("299.00")
    assert "price 249.00 does not appear on the page" in _feedback(chat)
    previous_turn = chat.calls[1][-2]
    assert previous_turn["role"] == "assistant"
    assert '"249.00"' in previous_turn["content"]


def test_gives_up_after_max_attempts(axel_request, good_answer):
    invented_platform = good_answer | {"platform": "Zoom"}
    with pytest.raises(ExtractionError, match="platform 'Zoom' is not mentioned"):
        LLMOfferingExtractor(ScriptedChat(invented_platform, invented_platform)).extract(axel_request)


def test_single_attempt_does_not_retry(axel_request, good_answer):
    chat = ScriptedChat(good_answer | {"platform": "Zoom"}, good_answer)
    with pytest.raises(ExtractionError):
        LLMOfferingExtractor(chat, max_attempts=1).extract(axel_request)
    assert len(chat.calls) == 1


def test_max_attempts_must_be_positive():
    with pytest.raises(ValueError, match="at least 1"):
        LLMOfferingExtractor(ScriptedChat(), max_attempts=0)


def test_invalid_json_is_retried(axel_request, good_answer):
    chat = ScriptedChat("Sure! Here is the JSON: {", good_answer)
    LLMOfferingExtractor(chat).extract(axel_request)
    assert "not valid JSON" in _feedback(chat)


def test_schema_violation_is_retried(axel_request, good_answer):
    chat = ScriptedChat(good_answer | {"rating": 5, "delivery": "by pigeon"}, good_answer)
    LLMOfferingExtractor(chat).extract(axel_request)
    assert "rating" in _feedback(chat)
    assert "delivery" in _feedback(chat)


def test_timezone_abbreviation_is_retried(axel_request, good_answer):
    bad = copy.deepcopy(good_answer)
    bad["schedule"]["timezone"] = "PDT"
    chat = ScriptedChat(bad, good_answer)
    LLMOfferingExtractor(chat).extract(axel_request)
    assert "unknown IANA timezone" in _feedback(chat)
