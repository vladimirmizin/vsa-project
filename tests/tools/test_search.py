from __future__ import annotations

import pytest

from vsa_commerce.errors import ToolInputError
from vsa_commerce.tools.search import normalize

ASSIGNMENT_QUERY = "I want to improve my Double Axel and I'm looking for an online program under $350."


def test_assignment_query_finds_double_axel_club_first(tools, ctx):
    response = tools.search_offerings(ctx, ASSIGNMENT_QUERY, max_price=350)
    top = response.results[0]
    assert top.offering_id == "double-axel-club"
    assert "matches goal 'double axel'" in top.match_reasons
    assert top.prices[0].price == "299.00 USD"


def test_same_price_everywhere_so_goal_decides(tools, ctx):
    # all three clubs cost $299: the budget alone cannot pick one
    response = tools.search_offerings(ctx, ASSIGNMENT_QUERY, max_price=350)
    assert {r.offering_id for r in response.results} >= {"double-jumps-club", "double-axel-club", "triple-jumps-club"}


@pytest.mark.parametrize("brand", ["Victory Skating", "VSA"])
def test_both_brand_names_are_returned(tools, ctx, brand):
    response = tools.search_offerings(ctx, f"Does {brand} have an online Double Axel training program?")
    assert {"Victory Skating", "VSA"} <= set(response.brand_names)
    assert response.results[0].offering_id == "double-axel-club"


def test_budget_excludes_with_a_reason(tools, ctx):
    response = tools.search_offerings(ctx, "double axel", max_price=200)
    clubs = {e.offering_id: e.reason for e in response.excluded}
    assert "above the 200 USD budget" in clubs["double-axel-club"]
    assert [r.offering_id for r in response.results] == ["private-lesson-marta"]


def test_nothing_fits_says_so(tools, ctx):
    response = tools.search_offerings(ctx, "anything", max_price=10)
    assert response.results == []
    assert response.note is not None


def test_generic_question_lists_programs_by_level(tools, ctx):
    ids = [r.offering_id for r in tools.search_offerings(ctx, "What does VSA offer?").results]
    assert ids == ["double-jumps-club", "double-axel-club", "triple-jumps-club", "private-lesson-marta"]


def test_level_in_query(tools, ctx):
    assert tools.search_offerings(ctx, "something for level 4").results[0].offering_id == "triple-jumps-club"


@pytest.mark.parametrize("budget", ["$350", "350", 350, 350.0, "1,000"])
def test_budget_formats(tools, ctx, budget):
    assert tools.search_offerings(ctx, "double axel", max_price=budget).results


@pytest.mark.parametrize("budget", ["cheap", "-5"])
def test_bad_budget(tools, ctx, budget):
    with pytest.raises(ToolInputError, match="max_price"):
        tools.search_offerings(ctx, "double axel", max_price=budget)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("My 2Axel!", "my double axel"),
        ("2-axel", "double axel"),
        ("Double-Axel", "double axel"),
        ("triples", "triple jumps"),
    ],
)
def test_normalize(text, expected):
    assert normalize(text) == expected
