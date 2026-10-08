"""Structured ranking over a small catalog: goals, level and budget. No embeddings needed at this size."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from vsa_commerce.domain.models import Catalog, Offering

_SYNONYMS = {
    r"\b2\s*-?\s*axel\b": "double axel",
    r"\bdouble-axel\b": "double axel",
    r"\b2a\b": "double axel",
    r"\btriples\b": "triple jumps",
    r"\bdoubles\b": "double jumps",
}
_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = {"a", "an", "and", "the", "for", "to", "of", "in", "on", "my", "i", "want", "online", "program", "club"}


def normalize(text: str) -> str:
    text = text.lower()
    for pattern, replacement in _SYNONYMS.items():
        text = re.sub(pattern, replacement, text)
    return " ".join(_WORD.findall(text))


@dataclass
class Match:
    offering: Offering
    score: int = 0
    reasons: list[str] = field(default_factory=list)


def rank(
    catalog: Catalog, query: str, *, max_price: Decimal | None, currency: str
) -> tuple[list[Match], list[tuple[Offering, str]]]:
    text = normalize(query)
    words = set(text.split()) - _STOPWORDS
    matches: list[Match] = []
    excluded: list[tuple[Offering, str]] = []

    for offering in catalog.offerings:
        if max_price is not None:
            affordable = [o for o in offering.offers if o.price.currency == currency and o.price.amount <= max_price]
            if not affordable:
                cheapest = min(offering.offers, key=lambda o: o.price.amount).price
                excluded.append((offering, f"cheapest option is {cheapest}, above the {max_price} {currency} budget"))
                continue

        match = Match(offering)
        matched_goals: list[str] = []
        # longest goals first, so "axel" adds nothing once "double axel" has matched
        for goal in sorted({normalize(g) for g in offering.audience.goals}, key=len, reverse=True):
            if goal and f" {goal} " in f" {text} " and not any(goal in longer for longer in matched_goals):
                matched_goals.append(goal)
                match.score += 3 + goal.count(" ")
                match.reasons.append(f"matches goal '{goal}'")
        level = offering.audience.level
        if level and normalize(level) in text:
            match.score += 3
            match.reasons.append(f"matches level '{level}'")
        overlap = sorted(words & set(normalize(offering.name).split()))
        if overlap:
            match.score += len(overlap)
            match.reasons.append(f"name contains {', '.join(overlap)}")
        if max_price is not None:
            match.reasons.append(f"within the {max_price} {currency} budget")
        matches.append(match)

    matches.sort(key=lambda m: (-m.score, m.offering.audience.level_rank is None, m.offering.audience.level_rank or 0))
    return matches, excluded
