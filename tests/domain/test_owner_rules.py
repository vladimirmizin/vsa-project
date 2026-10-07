from __future__ import annotations

import copy

import pytest

from vsa_commerce.domain.models import Catalog, EnrollmentMode
from vsa_commerce.domain.owner_rules import OwnerRule, OwnerRules, apply_owner_rules
from vsa_commerce.errors import OwnerRuleError


def _rules(*rules: OwnerRule, business_id: str = "victory-skating") -> OwnerRules:
    return OwnerRules(business_id=business_id, rules=list(rules))


ROLLING = OwnerRule(
    applies_to=["double-axel-club"],
    set={"enrollment.mode": "rolling", "enrollment.cohort_start_dates": []},
    reason="Runs every weekend",
    authority="Owner",
)


def test_rule_changes_field_and_is_recorded(vsa_source_data):
    catalog = Catalog.model_validate(apply_owner_rules(vsa_source_data, _rules(ROLLING)))
    offering = catalog.get("double-axel-club")
    assert offering.enrollment.mode is EnrollmentMode.ROLLING
    [override] = offering.provenance.overrides
    assert override.paths == ["enrollment.cohort_start_dates", "enrollment.mode"]
    assert override.authority == "Owner"


def test_source_facts_are_kept_next_to_the_override(vsa_source_data):
    catalog = Catalog.model_validate(apply_owner_rules(vsa_source_data, _rules(ROLLING)))
    assert catalog.get("double-axel-club").provenance.advertised["start_date"] == "Join us on October 10"


def test_other_offerings_untouched(vsa_source_data):
    catalog = Catalog.model_validate(apply_owner_rules(vsa_source_data, _rules(ROLLING)))
    assert catalog.get("triple-jumps-club").enrollment.mode is EnrollmentMode.COHORT
    assert catalog.get("triple-jumps-club").provenance.overrides == []


def test_input_is_not_mutated(vsa_source_data):
    before = copy.deepcopy(vsa_source_data)
    apply_owner_rules(vsa_source_data, _rules(ROLLING))
    assert vsa_source_data == before


def test_wildcard_applies_to_every_offering(vsa_source_data):
    rule = OwnerRule(applies_to=["*"], set={"platform": "Zoom"}, reason="r", authority="a")
    catalog = Catalog.model_validate(apply_owner_rules(vsa_source_data, _rules(rule)))
    assert {o.platform for o in catalog.offerings} == {"Zoom"}


def test_creates_missing_parent_objects():
    data = {"business": {"id": "b"}, "offerings": [{"id": "x"}]}
    rule = OwnerRule(applies_to=["x"], set={"audience.level": "Beginner"}, reason="r", authority="a")
    assert apply_owner_rules(data, _rules(rule, business_id="b"))["offerings"][0]["audience"] == {"level": "Beginner"}


def test_unknown_offering_is_an_error(vsa_source_data):
    rule = OwnerRule(applies_to=["ghost-club"], set={"name": "x"}, reason="r", authority="a")
    with pytest.raises(OwnerRuleError, match="ghost-club"):
        apply_owner_rules(vsa_source_data, _rules(rule))


def test_rules_for_another_business_are_rejected(vsa_source_data):
    with pytest.raises(OwnerRuleError, match="rules are for 'bloom'"):
        apply_owner_rules(vsa_source_data, _rules(ROLLING, business_id="bloom"))


def test_cannot_descend_into_a_scalar(vsa_source_data):
    rule = OwnerRule(applies_to=["double-axel-club"], set={"name.first": "x"}, reason="r", authority="a")
    with pytest.raises(OwnerRuleError, match="not an object"):
        apply_owner_rules(vsa_source_data, _rules(rule))


def test_shipped_rules_cover_all_three_clubs(vsa):
    for club in ("double-jumps-club", "double-axel-club", "triple-jumps-club"):
        offering = vsa.get(club)
        assert offering.enrollment.mode is EnrollmentMode.ROLLING
        assert offering.provenance.overrides, club
    assert "Victoria" in vsa.get("double-axel-club").provenance.overrides[0].authority
    assert "Assumption" in vsa.get("triple-jumps-club").provenance.overrides[0].authority
