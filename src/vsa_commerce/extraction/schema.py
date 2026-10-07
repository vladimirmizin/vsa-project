"""What the extractor receives and must return. Ids, provenance and checkout URLs are not the model's to decide."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from vsa_commerce.domain.models import (
    Audience,
    CheckoutMethod,
    CurriculumModule,
    DeliveryMode,
    EnrollmentPolicy,
    Money,
    OfferingKind,
    PriceUnit,
    RecurringSchedule,
    RelatedOffering,
    Slug,
    StaffMember,
)


class ExtractedOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Slug = Field(description="Short slug for this way of paying, e.g. 'six-month-package'.")
    name: str
    price: Money
    list_price: Money | None = Field(default=None, description="Crossed-out / pre-discount price, if shown.")
    unit: PriceUnit
    duration_months: int | None = None
    sessions_included: int | None = None
    terms: list[str] = Field(default_factory=list)
    checkout_method: CheckoutMethod
    checkout_url: str | None = Field(default=None, description="Must be one of the payment links provided.")
    checkout_label: str | None = Field(default=None, description="Button text, e.g. 'Register Now'.")


class ExtractedOffering(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: OfferingKind
    name: str
    summary: str = Field(description="One or two factual sentences a sales assistant could say as-is.")
    description: str = ""
    delivery: DeliveryMode
    platform: str | None = Field(default=None, description="Only if the page names it (e.g. 'Zoom').")
    audience: Audience = Field(default_factory=Audience)
    curriculum: list[CurriculumModule] = Field(default_factory=list)
    inclusions: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    staff: list[StaffMember] = Field(default_factory=list)
    schedule: RecurringSchedule | None = None
    enrollment: EnrollmentPolicy
    offers: list[ExtractedOffer] = Field(min_length=1)
    related: list[RelatedOffering] = Field(default_factory=list)
    advertised: dict[str, str] = Field(
        default_factory=dict, description="Verbatim claims worth keeping for reference (price per class, schedule)."
    )
    conflicts: list[str] = Field(default_factory=list, description="Statements on the page that contradict each other.")


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    business_id: str
    offering_id: str
    source_url: str
    fetched_on: date
    page_title: str
    page_text: str
    payment_links: list[str] = Field(default_factory=list)
    known_offering_ids: list[str] = Field(default_factory=list)

    @property
    def other_offering_ids(self) -> list[str]:
        return [i for i in self.known_offering_ids if i != self.offering_id]
