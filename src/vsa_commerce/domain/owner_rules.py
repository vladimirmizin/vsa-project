"""Owner rules applied on top of connector output; each application is recorded in provenance."""

from __future__ import annotations

import copy
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vsa_commerce.errors import OwnerRuleError

APPLIES_TO_ALL = "*"


class OwnerRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    applies_to: list[str] = Field(min_length=1, description="Offering ids, or ['*'] for every offering.")
    set: dict[str, Any] = Field(
        min_length=1, description="Dotted field paths to replace, e.g. {'enrollment.mode': 'rolling'}."
    )
    reason: str = Field(min_length=1)
    authority: str = Field(min_length=1)


class OwnerRules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    business_id: str
    rules: list[OwnerRule] = Field(default_factory=list)


def apply_owner_rules(catalog_data: dict[str, Any], owner_rules: OwnerRules) -> dict[str, Any]:
    # Works on raw data, before validation, so a rule can move an offering between valid states
    data = copy.deepcopy(catalog_data)
    business_id = data.get("business", {}).get("id")
    if business_id != owner_rules.business_id:
        raise OwnerRuleError(f"rules are for {owner_rules.business_id!r}, catalog is {business_id!r}")

    offerings: list[dict[str, Any]] = data.get("offerings", [])
    by_id = {o.get("id"): o for o in offerings}

    for rule in owner_rules.rules:
        if rule.applies_to == [APPLIES_TO_ALL]:
            targets = offerings
        else:
            unknown = [oid for oid in rule.applies_to if oid not in by_id]
            if unknown:
                raise OwnerRuleError(f"rule refers to unknown offerings: {unknown}")
            targets = [by_id[oid] for oid in rule.applies_to]

        for offering in targets:
            for path, value in rule.set.items():
                _set_path(offering, path, copy.deepcopy(value))
            provenance = offering.setdefault("provenance", {})
            provenance.setdefault("overrides", []).append(
                {"paths": sorted(rule.set), "reason": rule.reason, "authority": rule.authority}
            )
    return data


_ITEM = re.compile(r"^(?P<key>\w+)\[(?P<id>[^\]]+)\]$")


def _set_path(target: dict[str, Any], dotted: str, value: Any) -> None:
    """``enrollment.mode`` or ``offers[six-month-package].recurring``: list items are addressed by id."""
    *parents, leaf = dotted.split(".")
    node = target
    for segment in parents:
        node = _child(node, segment, dotted)
    node[leaf] = value


def _child(node: dict[str, Any], segment: str, dotted: str) -> dict[str, Any]:
    if match := _ITEM.match(segment):
        items = node.get(match["key"])
        found = [i for i in items or [] if isinstance(i, dict) and i.get("id") == match["id"]]
        if not found:
            raise OwnerRuleError(f"cannot set {dotted!r}: no item with id {match['id']!r} in {match['key']!r}")
        return found[0]
    child = node.get(segment)
    if child is None:
        child = node[segment] = {}
    if not isinstance(child, dict):
        raise OwnerRuleError(f"cannot set {dotted!r}: {segment!r} is not an object")
    return child
