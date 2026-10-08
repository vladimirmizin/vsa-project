"""The commerce tools, independent of how an assistant calls them (MCP, function calling, HTTP)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from vsa_commerce.catalog.store import CatalogStore
from vsa_commerce.domain.availability import check_availability
from vsa_commerce.domain.models import Catalog, EnrollmentMode, Offer, Offering, Weekday
from vsa_commerce.domain.sessions import upcoming_sessions
from vsa_commerce.errors import ToolInputError
from vsa_commerce.tools.checkout import build_checkout_url
from vsa_commerce.tools.search import rank
from vsa_commerce.tools.views import (
    AvailabilityView,
    CheckoutLink,
    Excluded,
    OfferingDetails,
    PriceView,
    RelatedView,
    ScheduleView,
    SearchResponse,
    SearchResult,
    SourceView,
    StaffView,
)
from vsa_commerce.tracking import Event, EventLog, EventType

log = logging.getLogger(__name__)

Clock = Callable[[], datetime]
STALE_AFTER = timedelta(days=7)

_CHECKOUT_INSTRUCTIONS = {
    "payment_link": "Open the link to pay securely on the provider's hosted checkout page.",
    "booking_page": "Open the link to choose a time and book.",
    "cart": "Open the link to review the cart and pay.",
    "in_app": "Install the business's app from the link and book there.",
    "contact": "Contact the business to complete the purchase.",
}


@dataclass(frozen=True, slots=True)
class CallContext:
    session_id: str
    channel: str


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CommerceTools:
    """One instance per business (tenant). Every call is recorded as a funnel event."""

    def __init__(self, store: CatalogStore, business_id: str, *, events: EventLog, clock: Clock = _utcnow) -> None:
        self.store = store
        self.business_id = business_id
        self.events = events
        self.clock = clock

    @property
    def catalog(self) -> Catalog:
        return self.store.load(self.business_id)

    # ---------------------------------------------------------------- tools

    def search_offerings(
        self, ctx: CallContext, query: str, max_price: float | str | None = None, currency: str = "USD"
    ) -> SearchResponse:
        started = time.perf_counter()
        catalog = self.catalog
        budget = _parse_amount(max_price)
        matches, excluded = rank(catalog, query, max_price=budget, currency=currency.upper())
        response = SearchResponse(
            session_id=ctx.session_id,
            business=catalog.business.name,
            brand_names=catalog.business.brand_names,
            query=query,
            results=[
                SearchResult(
                    offering_id=m.offering.id,
                    name=m.offering.name,
                    kind=m.offering.kind.value,
                    summary=m.offering.summary,
                    level=m.offering.audience.level,
                    prices=[_price_view(o) for o in m.offering.offers],
                    match_reasons=m.reasons,
                )
                for m in matches
            ],
            excluded=[Excluded(offering_id=o.id, name=o.name, reason=r) for o, r in excluded],
            note=None
            if matches
            else "Nothing fits these criteria; say so instead of suggesting something else as a match.",
        )
        self._track(
            ctx,
            EventType.SEARCH,
            None,
            {
                "query": query,
                "max_price": str(budget) if budget is not None else None,
                "results": [r.offering_id for r in response.results],
            },
            started,
        )
        return response

    def get_offering_details(self, ctx: CallContext, offering_id: str, timezone: str | None = None) -> OfferingDetails:
        started = time.perf_counter()
        catalog = self.catalog
        offering = self._offering(offering_id)
        now = self.clock()
        details = OfferingDetails(
            session_id=ctx.session_id,
            offering_id=offering.id,
            business=catalog.business.name,
            brand_names=catalog.business.brand_names,
            name=offering.name,
            kind=offering.kind.value,
            summary=offering.summary,
            description=offering.description,
            delivery=offering.delivery.value,
            platform=offering.platform,
            level=offering.audience.level,
            prerequisites=offering.audience.prerequisites,
            curriculum=[f"{m.title}: {'; '.join(m.points)}" if m.points else m.title for m in offering.curriculum],
            inclusions=offering.inclusions,
            requirements=offering.requirements,
            claims_by_business=offering.highlights,
            staff=[
                StaffView(name=s.name, role=s.role, days=[_day(d) for d in s.weekdays], bio=s.bio)
                for s in offering.staff
            ],
            schedule=self._schedule_view(offering, now, _check_timezone(timezone)),
            enrollment=_enrollment_text(offering),
            prices=[_price_view(o) for o in offering.offers],
            related=[
                RelatedView(
                    offering_id=r.offering_id,
                    name=catalog.get(r.offering_id).name,
                    relation=r.relation.value,
                    note=r.note,
                )
                for r in offering.related
            ],
            advertised_start_note=check_availability(offering, now=now).advertised_start_note,
            contact_email=catalog.business.contact_email,
            source=_source_view(offering, now),
        )
        self._track(ctx, EventType.OFFERING_VIEWED, offering.id, {}, started)
        return details

    def check_availability(
        self, ctx: CallContext, offering_id: str, date: str | None = None, timezone: str | None = None
    ) -> AvailabilityView:
        started = time.perf_counter()
        offering = self._offering(offering_id)
        requested = _parse_date(date)
        result = check_availability(
            offering, now=self.clock(), requested_date=requested, timezone=_check_timezone(timezone)
        )
        next_step = (
            "If the customer wants to join, create the checkout link with create_checkout_link."
            if result.can_join
            else "Explain why, and offer the next start date or a related offering."
        )
        self._track(
            ctx,
            EventType.AVAILABILITY_CHECKED,
            offering.id,
            {"requested_date": date, "timezone": result.timezone, "can_join": result.can_join},
            started,
        )
        return AvailabilityView(
            session_id=ctx.session_id, offering_name=offering.name, availability=result, next_step=next_step
        )

    def create_checkout_link(
        self,
        ctx: CallContext,
        offering_id: str,
        *,
        offer_id: str | None = None,
        email: str | None = None,
        timezone: str | None = None,
        date: str | None = None,
    ) -> CheckoutLink:
        started = time.perf_counter()
        offering = self._offering(offering_id)
        try:
            offer = offering.offer(offer_id)
        except KeyError:
            valid = ", ".join(o.id for o in offering.offers)
            raise ToolInputError(f"Unknown offer {offer_id!r} for {offering.id!r}. Valid offer ids: {valid}.") from None

        if offer.checkout.url is None:
            url, reference = "", None
        else:
            url, reference = build_checkout_url(offer.checkout, session_id=ctx.session_id, email=email)

        tz = _check_timezone(timezone)
        start = _parse_date(date)
        first_session = self._first_attendable_session(offering, tz, start)
        link = CheckoutLink(
            session_id=ctx.session_id,
            offering_id=offering.id,
            offering_name=offering.name,
            offer=_price_view(offer),
            checkout_url=url,
            method=offer.checkout.method.value,
            instructions=_CHECKOUT_INSTRUCTIONS[offer.checkout.method.value],
            what_happens_next=_what_happens_next(offering, offer, first_session),
            first_session=first_session,
            reference=reference,
            requested_date=start,
        )
        self._track(
            ctx,
            EventType.CHECKOUT_CREATED,
            offering.id,
            {
                "offer_id": offer.id,
                "amount": str(offer.price.amount),
                "currency": offer.price.currency,
                "reference": reference,
            },
            started,
        )
        return link

    # -------------------------------------------------------------- helpers

    def _offering(self, offering_id: str) -> Offering:
        try:
            return self.catalog.get(offering_id)
        except KeyError:
            valid = ", ".join(o.id for o in self.catalog.offerings)
            raise ToolInputError(
                f"Unknown offering {offering_id!r}. Valid ids: {valid}. Use search_offerings to find the right one."
            ) from None

    def _schedule_view(self, offering: Offering, now: datetime, customer_tz: str | None) -> ScheduleView | None:
        schedule = offering.schedule
        if schedule is None:
            return None
        zones = list(
            dict.fromkeys([*([customer_tz] if customer_tz else []), schedule.timezone, *schedule.display_timezones])
        )
        next_session = upcoming_sessions(schedule, now, 1)
        times = [f"{tz}: {next_session[0].in_timezone(tz).label()}" for tz in zones] if next_session else []
        return ScheduleView(
            days=[_day(d) for d in schedule.weekdays],
            duration_minutes=schedule.duration_minutes,
            sessions_per_week=schedule.sessions_per_week,
            times_this_week=times,
            note="Times are computed for the next session; local times can shift when clocks change.",
        )

    def _first_attendable_session(self, offering: Offering, tz: str | None, start: date | None) -> str | None:
        if offering.schedule is None:
            return None
        zone = tz or offering.schedule.timezone
        ready = self.clock() + timedelta(hours=offering.enrollment.access_lead_time_hours)
        if start is not None:
            ready = max(ready, datetime.combine(start, datetime.min.time(), tzinfo=ZoneInfo(zone)))
        sessions = upcoming_sessions(offering.schedule, ready, 1)
        return sessions[0].in_timezone(zone).label() if sessions else None

    def _track(
        self, ctx: CallContext, type_: EventType, offering_id: str | None, data: dict[str, Any], started: float
    ) -> None:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        event = Event(
            business_id=self.business_id,
            session_id=ctx.session_id,
            channel=ctx.channel,
            type=type_,
            offering_id=offering_id,
            data={**data, "elapsed_ms": elapsed_ms},
        )
        try:
            self.events.append(event)
        except OSError:
            log.exception("could not record %s event", type_.value)
        log.info(
            "tool %s business=%s session=%s offering=%s %.1fms",
            type_.value,
            self.business_id,
            ctx.session_id,
            offering_id,
            elapsed_ms,
        )


# ------------------------------------------------------------------ formatting


def _day(weekday: Weekday) -> str:
    return weekday.name.capitalize()


def _price_view(offer: Offer) -> PriceView:
    per_session = offer.price_per_session
    return PriceView(
        offer_id=offer.id,
        name=offer.name,
        price=str(offer.price),
        list_price=str(offer.list_price) if offer.list_price else None,
        discount_percent=offer.discount_percent,
        price_per_session=str(per_session) if per_session else None,
        billing=offer.billing_text(),
        refundable=offer.refundable,
        available=offer.available,
        cancellation_policy=offer.recurring.cancellation_policy if offer.recurring else None,
        duration_months=offer.duration_months,
        sessions_included=offer.sessions_included,
        terms=offer.terms,
        checkout_method=offer.checkout.method.value,
    )


def _enrollment_text(offering: Offering) -> str:
    policy = offering.enrollment
    match policy.mode:
        case EnrollmentMode.ROLLING:
            text = "Open continuously: join any time and start at the next scheduled session."
        case EnrollmentMode.COHORT:
            text = "Starts on fixed dates: " + ", ".join(d.isoformat() for d in policy.cohort_start_dates) + "."
        case EnrollmentMode.APPOINTMENT:
            text = "Booked per appointment."
        case EnrollmentMode.PURCHASE:
            text = "Can be purchased at any time."
    if policy.access_lead_time_hours:
        text += f" Access details arrive within {policy.access_lead_time_hours} hours of payment."
    return text


def _what_happens_next(offering: Offering, offer: Offer, first_session: str | None) -> list[str]:
    steps = []
    if offering.enrollment.access_lead_time_hours:
        steps.append(f"Access details arrive within {offering.enrollment.access_lead_time_hours} hours of payment.")
    if first_session:
        steps.append(f"Earliest session to plan for: {first_session}.")
    if offer.recurring:
        steps.append(f"Billing: {offer.billing_text()}.")
        if offer.recurring.cancellation_policy:
            steps.append(offer.recurring.cancellation_policy)
    if offer.refundable is False:
        steps.append("Payments are non-refundable.")
    return steps


def _source_view(offering: Offering, now: datetime) -> SourceView:
    fetched = offering.provenance.fetched_at
    return SourceView(
        url=str(offering.provenance.source_url),
        fetched_at=fetched,
        data_age_days=max((now - fetched).days, 0),
        stale=now - fetched > STALE_AFTER,
        owner_rules=[f"{o.reason} ({o.authority})" for o in offering.provenance.overrides],
    )


# --------------------------------------------------------------------- parsing


def _parse_amount(value: float | str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except InvalidOperation:
        raise ToolInputError(f"max_price must be a number, got {value!r}.") from None
    if amount < 0:
        raise ToolInputError("max_price cannot be negative.")
    return amount.quantize(Decimal("0.01"))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolInputError(f"date must be an ISO date like 2026-11-06, got {value!r}.") from None


def _check_timezone(value: str | None) -> str | None:
    if not value:
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolInputError(
            f"Unknown timezone {value!r}. Use an IANA name such as 'America/New_York' or 'Europe/London'."
        ) from None
    return value
