"""Conversion funnel and sales signals from the event log."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from vsa_commerce.tracking.events import FUNNEL, Event, EventType


class FunnelStep(BaseModel):
    step: EventType
    sessions: int
    rate_from_previous: float | None


class FunnelReport(BaseModel):
    business_id: str
    sessions: int
    steps: list[FunnelStep]
    checkouts_by_offering: dict[str, int]
    sessions_by_channel: dict[str, int]
    top_queries: list[tuple[str, int]]
    budgets_mentioned: list[str]
    requested_dates: list[str]


def funnel_report(events: Iterable[Event], business_id: str, *, top: int = 10) -> FunnelReport:
    own = [e for e in events if e.business_id == business_id]
    reached: dict[EventType, set[str]] = defaultdict(set)
    channels: dict[str, set[str]] = defaultdict(set)
    checkouts: Counter[str] = Counter()
    queries: Counter[str] = Counter()
    budgets: list[str] = []
    dates: list[str] = []

    for event in own:
        reached[event.type].add(event.session_id)
        channels[event.channel].add(event.session_id)
        if event.type is EventType.SEARCH:
            if query := str(event.data.get("query") or "").strip().lower():
                queries[query] += 1
            if event.data.get("max_price") is not None:
                budgets.append(str(event.data["max_price"]))
        elif event.type is EventType.AVAILABILITY_CHECKED and event.data.get("requested_date"):
            dates.append(str(event.data["requested_date"]))
        elif event.type is EventType.CHECKOUT_CREATED and event.offering_id:
            checkouts[event.offering_id] += 1

    steps: list[FunnelStep] = []
    previous: int | None = None
    for step in FUNNEL:
        count = len(reached[step])
        rate = round(count / previous, 3) if previous else None
        steps.append(FunnelStep(step=step, sessions=count, rate_from_previous=rate))
        previous = count

    return FunnelReport(
        business_id=business_id,
        sessions=len({e.session_id for e in own}),
        steps=steps,
        checkouts_by_offering=dict(checkouts),
        sessions_by_channel={channel: len(ids) for channel, ids in sorted(channels.items())},
        top_queries=queries.most_common(top),
        budgets_mentioned=budgets,
        requested_dates=dates,
    )
