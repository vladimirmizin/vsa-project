from __future__ import annotations

from datetime import date, time
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from vsa_commerce.domain.models.base import Model, Timezone, Weekday


class RecurringSchedule(Model):
    """Weekly slot anchored in one timezone; times elsewhere are computed, never stored."""

    weekdays: list[Weekday] = Field(min_length=1)
    start_time: time
    duration_minutes: Annotated[int, Field(gt=0, le=24 * 60)]
    timezone: Timezone
    display_timezones: list[Timezone] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays must be unique")
        if self.start_time.tzinfo is not None:
            raise ValueError("start_time must be naive; the timezone field anchors it")
        return self

    @property
    def sessions_per_week(self) -> int:
        return len(self.weekdays)


class EnrollmentMode(StrEnum):
    ROLLING = "rolling"
    COHORT = "cohort"
    APPOINTMENT = "appointment"
    PURCHASE = "purchase"


class EnrollmentPolicy(Model):
    mode: EnrollmentMode
    cohort_start_dates: list[date] = Field(default_factory=list)
    access_lead_time_hours: Annotated[int, Field(ge=0)] = Field(
        default=0, description="How long after payment the customer receives access."
    )
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cohort_dates_match_mode(self) -> Self:
        if self.mode is EnrollmentMode.COHORT and not self.cohort_start_dates:
            raise ValueError("cohort enrollment requires at least one cohort_start_date")
        if self.mode is not EnrollmentMode.COHORT and self.cohort_start_dates:
            raise ValueError("cohort_start_dates only make sense for cohort enrollment")
        return self
