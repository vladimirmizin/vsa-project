from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from vsa_commerce.domain.models.base import Model, NonEmptyStr, Slug, Weekday
from vsa_commerce.domain.models.pricing import Offer
from vsa_commerce.domain.models.schedule import EnrollmentPolicy, RecurringSchedule

ADVERTISED_START_KEY = "start_date"


class OfferingKind(StrEnum):
    COURSE = "course"
    SERVICE = "service"
    PRODUCT = "product"


class DeliveryMode(StrEnum):
    ONLINE = "online"
    IN_PERSON = "in_person"
    HYBRID = "hybrid"
    SHIPPED = "shipped"


class RelationKind(StrEnum):
    PREREQUISITE = "prerequisite"
    NEXT_STEP = "next_step"
    ADD_ON = "add_on"


class Audience(Model):
    level: str | None = None
    level_rank: int | None = Field(default=None, description="Higher is more advanced.")
    prerequisites: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list, description="Outcomes customers ask for in their own words.")


class CurriculumModule(Model):
    title: NonEmptyStr
    points: list[str] = Field(default_factory=list)


class StaffMember(Model):
    name: NonEmptyStr
    role: NonEmptyStr
    bio: str | None = None
    weekdays: list[Weekday] = Field(default_factory=list, description="Days this person leads sessions.")


class RelatedOffering(Model):
    offering_id: Slug
    relation: RelationKind
    note: str | None = None


class Override(Model):
    paths: list[NonEmptyStr] = Field(min_length=1)
    reason: NonEmptyStr
    authority: NonEmptyStr


class Provenance(Model):
    source_url: HttpUrl
    platform: NonEmptyStr
    fetched_at: AwareDatetime
    advertised: dict[str, str] = Field(
        default_factory=dict, description="Verbatim claims from the source; not used for business logic."
    )
    conflicts: list[str] = Field(default_factory=list)
    overrides: list[Override] = Field(default_factory=list)


class Offering(Model):
    id: Slug
    business_id: Slug
    kind: OfferingKind
    name: NonEmptyStr
    summary: NonEmptyStr
    description: str = ""
    delivery: DeliveryMode
    platform: str | None = None
    audience: Audience = Field(default_factory=Audience)
    curriculum: list[CurriculumModule] = Field(default_factory=list)
    inclusions: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list, description="Marketing claims as stated by the business.")
    staff: list[StaffMember] = Field(default_factory=list)
    schedule: RecurringSchedule | None = None
    enrollment: EnrollmentPolicy
    offers: list[Offer] = Field(min_length=1)
    related: list[RelatedOffering] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def _unique_offer_ids(self) -> Self:
        ids = [offer.id for offer in self.offers]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate offer ids in offering {self.id!r}")
        return self

    def offer(self, offer_id: str | None = None) -> Offer:
        if offer_id is None:
            return self.offers[0]
        for offer in self.offers:
            if offer.id == offer_id:
                return offer
        raise KeyError(offer_id)
