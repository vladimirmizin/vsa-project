"""Whether a customer can start around a date. Decided by enrollment rules, never by dates on the landing page."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict

from vsa_commerce.domain.models import ADVERTISED_START_KEY, EnrollmentMode, EnrollmentPolicy, Offering
from vsa_commerce.domain.sessions import Session, upcoming_sessions

DEFAULT_SESSION_COUNT = 4


class SessionSlot(BaseModel):
    model_config = ConfigDict(frozen=True)

    starts_at: AwareDatetime
    ends_at: AwareDatetime
    label: str

    @classmethod
    def from_session(cls, session: Session) -> SessionSlot:
        return cls(starts_at=session.start, ends_at=session.end, label=session.label())


class AvailabilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    offering_id: str
    can_join: bool
    enrollment_mode: EnrollmentMode
    requested_date: date | None
    timezone: str
    explanation: str
    notes: list[str]
    upcoming_sessions: list[SessionSlot]
    enroll_by: AwareDatetime | None = None
    next_cohort_date: date | None = None
    advertised_start_note: str | None = None


def check_availability(
    offering: Offering,
    *,
    now: datetime,
    requested_date: date | None = None,
    timezone: str | None = None,
    session_count: int = DEFAULT_SESSION_COUNT,
) -> AvailabilityResult:
    """``timezone`` is the customer's; session times are returned in it."""
    if now.tzinfo is None:
        raise ValueError("'now' must be timezone-aware")

    tz_name = timezone or (offering.schedule.timezone if offering.schedule else "UTC")
    zone = ZoneInfo(tz_name)
    in_past = requested_date is not None and requested_date < now.astimezone(zone).date()
    earliest = now
    if requested_date is not None and not in_past:
        earliest = max(now, datetime.combine(requested_date, time.min, tzinfo=zone))

    policy = offering.enrollment
    next_cohort: date | None = None
    sessions_from: datetime | None = earliest

    match policy.mode:
        case EnrollmentMode.COHORT:
            next_cohort = _next_cohort(policy, earliest.astimezone(zone).date())
            if next_cohort is None:
                sessions_from = None
                explanation = "There is no upcoming start date for this offering."
            else:
                anchor = ZoneInfo(offering.schedule.timezone) if offering.schedule else zone
                sessions_from = max(earliest, datetime.combine(next_cohort, time.min, tzinfo=anchor))
                explanation = (
                    f"Enrollment is by group start dates; the next group starts on {next_cohort:%A, %d %B %Y}."
                )
        case EnrollmentMode.ROLLING:
            explanation = "Enrollment is open continuously; new participants start at the next scheduled session."
        case EnrollmentMode.APPOINTMENT:
            explanation = "Booked per appointment; the customer chooses a time when booking."
        case EnrollmentMode.PURCHASE:
            explanation = "Can be purchased at any time."

    slots = _slots(offering, sessions_from, tz_name, session_count)
    enroll_by = None
    if slots and policy.access_lead_time_hours:
        enroll_by = slots[0].starts_at - timedelta(hours=policy.access_lead_time_hours)

    notes: list[str] = []
    if in_past and requested_date is not None:
        notes.append(f"{requested_date:%d %B %Y} is already in the past, so the options are listed from today.")
    if slots and policy.mode is not EnrollmentMode.PURCHASE:
        notes.append(f"First session from the requested time: {slots[0].label}.")
    if enroll_by is not None and enroll_by < now:
        notes.append(
            f"Access details arrive up to {policy.access_lead_time_hours} hours after payment, so the first "
            "listed session may come too soon; the following sessions are listed as well."
        )

    return AvailabilityResult(
        offering_id=offering.id,
        can_join=sessions_from is not None,
        enrollment_mode=policy.mode,
        requested_date=requested_date,
        timezone=tz_name,
        explanation=explanation,
        notes=notes,
        upcoming_sessions=slots,
        enroll_by=enroll_by,
        next_cohort_date=next_cohort,
        advertised_start_note=_advertised_start_note(offering),
    )


def _next_cohort(policy: EnrollmentPolicy, on_or_after: date) -> date | None:
    return min((d for d in policy.cohort_start_dates if d >= on_or_after), default=None)


def _slots(offering: Offering, start: datetime | None, tz_name: str, count: int) -> list[SessionSlot]:
    if offering.schedule is None or start is None:
        return []
    sessions = upcoming_sessions(offering.schedule, start, count)
    return [SessionSlot.from_session(s.in_timezone(tz_name)) for s in sessions]


def _advertised_start_note(offering: Offering) -> str | None:
    claim = offering.provenance.advertised.get(ADVERTISED_START_KEY)
    if claim is None or offering.enrollment.mode is not EnrollmentMode.ROLLING:
        return None
    return (
        f'The source page says "{claim}". That is one start of a recurring program, not the only '
        "one and not an enrollment deadline: new participants can join at any upcoming session."
    )
