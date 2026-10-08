"""What the assistant receives. Shaped for answering a customer, not mirroring the catalog schema."""

from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict

from vsa_commerce.domain.availability import AvailabilityResult


class View(BaseModel):
    model_config = ConfigDict(frozen=True)


class PriceView(View):
    offer_id: str
    name: str
    price: str
    list_price: str | None = None
    discount_percent: int | None = None
    price_per_session: str | None = None
    billing: str
    refundable: bool | None = None
    cancellation_policy: str | None = None
    duration_months: int | None = None
    sessions_included: int | None = None
    terms: list[str] = []
    checkout_method: str


class SearchResult(View):
    offering_id: str
    name: str
    kind: str
    summary: str
    level: str | None
    prices: list[PriceView]
    match_reasons: list[str]


class Excluded(View):
    offering_id: str
    name: str
    reason: str


class SearchResponse(View):
    session_id: str
    business: str
    brand_names: list[str]
    query: str
    results: list[SearchResult]
    excluded: list[Excluded]
    note: str | None = None


class ScheduleView(View):
    days: list[str]
    duration_minutes: int
    sessions_per_week: int
    times_this_week: list[str]
    note: str


class StaffView(View):
    name: str
    role: str
    days: list[str]
    bio: str | None


class RelatedView(View):
    offering_id: str
    name: str
    relation: str
    note: str | None


class SourceView(View):
    url: str
    fetched_at: AwareDatetime
    data_age_days: int
    stale: bool
    owner_rules: list[str]


class OfferingDetails(View):
    session_id: str
    offering_id: str
    business: str
    brand_names: list[str]
    name: str
    kind: str
    summary: str
    description: str
    delivery: str
    platform: str | None
    level: str | None
    prerequisites: list[str]
    curriculum: list[str]
    inclusions: list[str]
    requirements: list[str]
    claims_by_business: list[str]
    staff: list[StaffView]
    schedule: ScheduleView | None
    enrollment: str
    prices: list[PriceView]
    related: list[RelatedView]
    advertised_start_note: str | None
    contact_email: str | None
    source: SourceView


class AvailabilityView(View):
    session_id: str
    offering_name: str
    availability: AvailabilityResult
    next_step: str


class CheckoutLink(View):
    session_id: str
    offering_id: str
    offering_name: str
    offer: PriceView
    checkout_url: str
    method: str
    instructions: str
    what_happens_next: list[str]
    first_session: str | None
    reference: str | None
    requested_date: date | None = None
