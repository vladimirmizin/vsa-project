from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from vsa_commerce.errors import ToolInputError
from vsa_commerce.tools import CommerceTools
from vsa_commerce.tracking import EventType

AXEL = "double-axel-club"


class TestDetails:
    def test_everything_the_assignment_asks_for(self, tools, ctx):
        d = tools.get_offering_details(ctx, AXEL)
        assert d.name == "6-Month Double Axel Club"
        assert {"Victory Skating", "VSA"} <= set(d.brand_names)
        assert d.delivery == "online"
        assert "Double Axel" in d.summary
        assert d.prices[0].price == "299.00 USD"
        assert d.prices[0].duration_months == 6
        assert d.prices[0].sessions_included == 48
        assert d.staff[0].name == "Coach Marta"
        assert d.schedule is not None
        assert d.schedule.days == ["Saturday", "Sunday"]
        assert d.schedule.duration_minutes == 45
        assert d.description
        assert d.level == "Level 3"
        assert d.prerequisites == ["Proficiency in double jumps off-ice"]
        assert d.enrollment.startswith("Open continuously")
        assert d.prices[0].checkout_method == "payment_link"

    def test_billing_terms_are_explicit(self, tools, ctx):
        price = tools.get_offering_details(ctx, AXEL).prices[0]
        assert price.billing == "299.00 USD every 6 months, renews automatically until cancelled"
        assert price.refundable is False
        assert "48 hours" in (price.cancellation_policy or "")
        assert price.list_price == "699.00 USD"
        assert price.discount_percent == 57
        assert price.price_per_session == "6.23 USD"

    def test_unknown_billing_is_not_called_one_time(self, tools, ctx):
        price = tools.get_offering_details(ctx, "triple-jumps-club").prices[0]
        assert price.billing == "299.00 USD for 6 months"
        assert price.refundable is None

    def test_hourly_service(self, tools, ctx):
        assert tools.get_offering_details(ctx, "private-lesson-marta").prices[0].billing == "60.00 USD per hour"

    def test_schedule_in_customer_timezone_first(self, store, events, ctx):
        november = CommerceTools(
            store, "victory-skating", events=events, clock=lambda: datetime(2026, 11, 2, tzinfo=UTC)
        )
        times = november.get_offering_details(ctx, AXEL, timezone="Asia/Bangkok").schedule.times_this_week
        assert times[0] == "Asia/Bangkok: Sat 7 Nov 2026, 22:00-22:45 UTC+07"
        assert "America/Los_Angeles: Sat 7 Nov 2026, 07:00-07:45 PST" in times

    def test_related_offerings_are_named(self, tools, ctx):
        related = {r.offering_id: (r.name, r.relation) for r in tools.get_offering_details(ctx, AXEL).related}
        assert related["triple-jumps-club"] == ("6-Month Triple Jumps Club", "next_step")

    def test_advertised_date_is_explained(self, tools, ctx):
        assert "Join us on October 10" in (tools.get_offering_details(ctx, AXEL).advertised_start_note or "")

    def test_source_freshness(self, store, events, ctx, now):
        fresh = CommerceTools(store, "victory-skating", events=events, clock=lambda: now)
        old = CommerceTools(store, "victory-skating", events=events, clock=lambda: now + timedelta(days=30))
        assert fresh.get_offering_details(ctx, AXEL).source.stale is False
        source = old.get_offering_details(ctx, AXEL).source
        assert source.stale is True
        assert source.data_age_days == 30
        assert any("Victoria" in rule for rule in source.owner_rules)

    def test_unknown_offering_lists_valid_ids(self, tools, ctx):
        with pytest.raises(ToolInputError, match="Valid ids: double-jumps-club, double-axel-club"):
            tools.get_offering_details(ctx, "quad-club")

    def test_bad_timezone(self, tools, ctx):
        with pytest.raises(ToolInputError, match="IANA name"):
            tools.get_offering_details(ctx, AXEL, timezone="PST")


class TestAvailability:
    def test_free_on_november_6(self, tools, ctx):
        view = tools.check_availability(ctx, AXEL, "2026-11-06")
        assert view.availability.can_join is True
        assert view.availability.upcoming_sessions[0].label == "Sat 7 Nov 2026, 07:00-07:45 PST"
        assert "create_checkout_link" in view.next_step

    def test_bad_date(self, tools, ctx):
        with pytest.raises(ToolInputError, match="ISO date"):
            tools.check_availability(ctx, AXEL, "November 6")

    def test_no_date(self, tools, ctx):
        assert tools.check_availability(ctx, AXEL).availability.requested_date is None


class TestCheckout:
    def test_stripe_link_carries_the_session_for_attribution(self, tools, ctx):
        link = tools.create_checkout_link(ctx, AXEL)
        parts = urlsplit(link.checkout_url)
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://buy.stripe.com/14AeVd6anbti69kcJ9dMM1M"
        assert parse_qs(parts.query) == {"client_reference_id": ["session-1"]}
        assert link.reference == "session-1"

    def test_email_is_prefilled(self, tools, ctx):
        query = parse_qs(urlsplit(tools.create_checkout_link(ctx, AXEL, email="skater@example.com").checkout_url).query)
        assert query["prefilled_email"] == ["skater@example.com"]

    def test_terms_and_next_steps(self, tools, ctx):
        link = tools.create_checkout_link(ctx, AXEL)
        assert link.offer.billing.endswith("renews automatically until cancelled")
        assert "Access details arrive within 24 hours of payment." in link.what_happens_next
        assert "Payments are non-refundable." in link.what_happens_next
        assert link.first_session == "Sat 10 Oct 2026, 07:00-07:45 PDT"

    def test_first_session_respects_access_lead_time(self, store, events, ctx):
        friday_noon_la = datetime(2026, 11, 6, 20, 0, tzinfo=UTC)
        late = CommerceTools(store, "victory-skating", events=events, clock=lambda: friday_noon_la)
        assert late.create_checkout_link(ctx, AXEL).first_session == "Sun 8 Nov 2026, 07:00-07:45 PST"

    def test_first_session_from_the_requested_start_date(self, tools, ctx):
        link = tools.create_checkout_link(ctx, AXEL, date="2026-11-06")
        assert link.first_session == "Sat 7 Nov 2026, 07:00-07:45 PST"
        assert link.requested_date.isoformat() == "2026-11-06"

    def test_first_session_in_customer_timezone(self, tools, ctx):
        link = tools.create_checkout_link(ctx, AXEL, timezone="Europe/London")
        assert link.first_session == "Sat 10 Oct 2026, 15:00-15:45 BST"

    def test_unsafe_session_id_is_sanitised(self, tools):
        from vsa_commerce.tools import CallContext

        link = tools.create_checkout_link(CallContext(session_id="a b/c", channel="test"), AXEL)
        assert link.reference == "a-b-c"

    def test_app_booking_has_no_payment_reference(self, tools, ctx):
        link = tools.create_checkout_link(ctx, "private-lesson-marta")
        assert link.method == "in_app"
        assert link.checkout_url == "https://vsaworld.com/download/"
        assert link.reference is None
        assert "app" in link.instructions
        assert link.first_session is None

    def test_unknown_offer(self, tools, ctx):
        with pytest.raises(ToolInputError, match="Valid offer ids: six-month-package"):
            tools.create_checkout_link(ctx, AXEL, offer_id="monthly")


class TestTracking:
    def test_every_call_is_an_event(self, tools, ctx, events):
        tools.search_offerings(ctx, "double axel", max_price=350)
        tools.get_offering_details(ctx, AXEL)
        tools.check_availability(ctx, AXEL, "2026-11-06")
        tools.create_checkout_link(ctx, AXEL)
        recorded = events.read()
        assert [e.type for e in recorded] == [
            EventType.SEARCH,
            EventType.OFFERING_VIEWED,
            EventType.AVAILABILITY_CHECKED,
            EventType.CHECKOUT_CREATED,
        ]
        assert {e.session_id for e in recorded} == {"session-1"}
        assert {e.channel for e in recorded} == {"test"}
        assert recorded[0].data["max_price"] == "350.00"
        assert recorded[2].data["requested_date"] == "2026-11-06"
        assert recorded[3].data["reference"] == "session-1"
        assert all("elapsed_ms" in e.data for e in recorded)

    def test_failed_lookup_is_not_tracked(self, tools, ctx, events):
        with pytest.raises(ToolInputError):
            tools.get_offering_details(ctx, "nope")
        assert events.read() == []

    def test_broken_event_log_does_not_break_the_tool(self, store, ctx, now):
        class Full:
            def append(self, event):
                raise OSError("disk full")

            def read(self):
                return []

        tools = CommerceTools(store, "victory-skating", events=Full(), clock=lambda: now)
        assert tools.search_offerings(ctx, "double axel").results
