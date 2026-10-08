from __future__ import annotations

from typing import Any, ClassVar

from vsa_commerce.tracking import Event, EventType, InMemoryEventLog, JsonlEventLog, funnel_report
from vsa_commerce.tracking.attribution import payment_event_from_stripe

BIZ = "victory-skating"


def _event(session: str, type_: EventType, **kwargs) -> Event:
    return Event(
        business_id=kwargs.pop("business_id", BIZ),
        session_id=session,
        channel=kwargs.pop("channel", "mcp"),
        type=type_,
        **kwargs,
    )


class TestJsonlLog:
    def test_round_trip(self, tmp_path):
        log = JsonlEventLog(tmp_path / "var" / "events.jsonl")
        event = _event("s1", EventType.SEARCH, data={"query": "double axel"})
        log.append(event)
        assert log.read() == [event]

    def test_missing_file_is_empty(self, tmp_path):
        assert JsonlEventLog(tmp_path / "none.jsonl").read() == []

    def test_unreadable_lines_are_skipped(self, tmp_path):
        path = tmp_path / "events.jsonl"
        log = JsonlEventLog(path)
        log.append(_event("s1", EventType.SEARCH))
        with path.open("a", encoding="utf-8") as fh:
            fh.write("not json\n\n")
        log.append(_event("s2", EventType.SEARCH))
        assert [e.session_id for e in log.read()] == ["s1", "s2"]


class TestFunnel:
    def test_sessions_per_step_and_conversion(self):
        log = InMemoryEventLog()
        for session in ("a", "b", "c", "d"):
            log.append(_event(session, EventType.SEARCH, data={"query": "Double Axel", "max_price": "350"}))
        for session in ("a", "b"):
            log.append(_event(session, EventType.OFFERING_VIEWED, offering_id="double-axel-club"))
            log.append(_event(session, EventType.AVAILABILITY_CHECKED, data={"requested_date": "2026-11-06"}))
        log.append(_event("a", EventType.CHECKOUT_CREATED, offering_id="double-axel-club"))
        log.append(_event("a", EventType.PAYMENT_COMPLETED, channel="stripe"))
        log.append(_event("z", EventType.SEARCH, business_id="someone-else"))

        report = funnel_report(log.read(), BIZ)
        assert report.sessions == 4
        assert [(s.step, s.sessions, s.rate_from_previous) for s in report.steps] == [
            (EventType.SEARCH, 4, None),
            (EventType.OFFERING_VIEWED, 2, 0.5),
            (EventType.AVAILABILITY_CHECKED, 2, 1.0),
            (EventType.CHECKOUT_CREATED, 1, 0.5),
            (EventType.PAYMENT_COMPLETED, 1, 1.0),
        ]
        assert report.checkouts_by_offering == {"double-axel-club": 1}
        assert report.top_queries == [("double axel", 4)]
        assert report.budgets_mentioned == ["350"] * 4
        assert report.requested_dates == ["2026-11-06"] * 2
        assert report.sessions_by_channel == {"mcp": 4, "stripe": 1}

    def test_empty_log(self):
        report = funnel_report([], BIZ)
        assert report.sessions == 0
        assert all(s.sessions == 0 and s.rate_from_previous is None for s in report.steps)


class TestStripeAttribution:
    PAYLOAD: ClassVar[dict[str, Any]] = {
        "type": "checkout.session.completed",
        "created": 1791374400,
        "data": {
            "object": {
                "id": "cs_test_123",
                "client_reference_id": "session-1",
                "amount_total": 29900,
                "currency": "usd",
                "payment_link": "plink_123",
            }
        },
    }

    def test_paid_checkout_joins_the_ai_session(self):
        event = payment_event_from_stripe(self.PAYLOAD, business_id=BIZ)
        assert event is not None
        assert event.type is EventType.PAYMENT_COMPLETED
        assert event.session_id == "session-1"
        assert event.data["amount_total"] == 29900
        assert event.at.year == 2026

    def test_other_events_are_ignored(self):
        assert payment_event_from_stripe({"type": "invoice.paid"}, business_id=BIZ) is None

    def test_payment_without_reference_is_not_attributed(self):
        payload = {"type": "checkout.session.completed", "data": {"object": {"id": "cs_1"}}}
        assert payment_event_from_stripe(payload, business_id=BIZ) is None
