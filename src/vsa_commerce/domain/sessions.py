"""Expanding a weekly schedule into concrete sessions. DST is handled by zoneinfo, never by hand."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from vsa_commerce.domain.models import RecurringSchedule

_MAX_DAYS_SCANNED = 366 * 2


@dataclass(frozen=True, slots=True)
class Session:
    start: datetime
    end: datetime

    def in_timezone(self, tz: str) -> Session:
        zone = ZoneInfo(tz)
        return Session(start=self.start.astimezone(zone), end=self.end.astimezone(zone))

    def label(self) -> str:
        """E.g. ``Sat 7 Nov 2026, 07:00-07:45 PST``."""
        return (
            f"{self.start:%a} {self.start.day} {self.start:%b %Y}, "
            f"{self.start:%H:%M}-{self.end:%H:%M} {timezone_abbreviation(self.start)}"
        )


def timezone_abbreviation(moment: datetime) -> str:
    name = moment.tzname() or ""
    return f"UTC{name}" if name[:1] in ("+", "-") else name


def upcoming_sessions(schedule: RecurringSchedule, after: datetime, limit: int) -> list[Session]:
    """First ``limit`` sessions starting at or after ``after``, in the schedule's anchor timezone."""
    if after.tzinfo is None:
        raise ValueError("'after' must be timezone-aware")
    if limit <= 0:
        return []

    anchor = ZoneInfo(schedule.timezone)
    weekdays = set(schedule.weekdays)
    duration = timedelta(minutes=schedule.duration_minutes)
    day = after.astimezone(anchor).date()

    sessions: list[Session] = []
    for _ in range(_MAX_DAYS_SCANNED):
        if day.weekday() in weekdays:
            # UTC round trip normalises a wall time that falls into a DST gap
            start_utc = datetime.combine(day, schedule.start_time, tzinfo=anchor).astimezone(UTC)
            if start_utc >= after:
                end_utc = start_utc + duration
                sessions.append(Session(start=start_utc.astimezone(anchor), end=end_utc.astimezone(anchor)))
                if len(sessions) == limit:
                    break
        day += timedelta(days=1)
    return sessions
