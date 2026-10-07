"""2026 clock changes: Europe on 25 Oct, US on 1 Nov, Thailand never."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from vsa_commerce.domain.models import RecurringSchedule
from vsa_commerce.domain.sessions import Session, timezone_abbreviation, upcoming_sessions

LA = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def schedule(vsa) -> RecurringSchedule:
    return vsa.get("double-axel-club").schedule


def _first_on(schedule: RecurringSchedule, day: date) -> Session:
    session = upcoming_sessions(schedule, datetime(day.year, day.month, day.day, tzinfo=LA), 1)[0]
    assert session.start.date() == day
    return session


def _local(session: Session, tz: str) -> str:
    local = session.in_timezone(tz).start
    return f"{local:%H:%M} {timezone_abbreviation(local)}"


class TestUpcomingSessions:
    def test_only_saturdays_and_sundays(self, schedule, now):
        sessions = upcoming_sessions(schedule, now, 8)
        assert len(sessions) == 8
        assert {s.start.weekday() for s in sessions} == {5, 6}

    def test_sessions_last_45_minutes(self, schedule, now):
        assert all((s.end - s.start).total_seconds() == 45 * 60 for s in upcoming_sessions(schedule, now, 4))

    def test_first_session_after_build_day_is_october_10(self, schedule, now):
        assert upcoming_sessions(schedule, now, 1)[0].start == datetime(2026, 10, 10, 7, 0, tzinfo=LA)

    def test_session_that_already_started_is_not_upcoming(self, schedule):
        during_class = datetime(2026, 10, 10, 7, 10, tzinfo=LA)
        assert upcoming_sessions(schedule, during_class, 1)[0].start.date() == date(2026, 10, 11)

    def test_session_starting_exactly_now_is_included(self, schedule):
        start = datetime(2026, 10, 10, 7, 0, tzinfo=LA)
        assert upcoming_sessions(schedule, start, 1)[0].start == start

    def test_after_given_in_another_timezone(self, schedule):
        bangkok_friday_night = datetime(2026, 11, 6, 23, 30, tzinfo=ZoneInfo("Asia/Bangkok"))
        assert upcoming_sessions(schedule, bangkok_friday_night, 1)[0].start == datetime(2026, 11, 7, 7, 0, tzinfo=LA)

    def test_naive_datetime_rejected(self, schedule):
        with pytest.raises(ValueError, match="timezone-aware"):
            upcoming_sessions(schedule, datetime(2026, 10, 7), 1)  # noqa: DTZ001 - the point of the test

    def test_zero_limit(self, schedule, now):
        assert upcoming_sessions(schedule, now, 0) == []


class TestTimezones:
    def test_landing_page_labels_hold_in_october(self, schedule):
        session = _first_on(schedule, date(2026, 10, 10))
        assert _local(session, "America/Los_Angeles") == "07:00 PDT"
        assert _local(session, "America/Denver") == "08:00 MDT"
        assert _local(session, "America/Chicago") == "09:00 CDT"
        assert _local(session, "America/New_York") == "10:00 EDT"
        assert _local(session, "Europe/London") == "15:00 BST"
        assert _local(session, "Europe/Berlin") == "16:00 CEST"
        assert _local(session, "Asia/Bangkok") == "21:00 UTC+07"

    def test_week_between_eu_and_us_clock_changes(self, schedule):
        session = _first_on(schedule, date(2026, 10, 31))
        assert _local(session, "America/Los_Angeles") == "07:00 PDT"
        assert _local(session, "Europe/London") == "14:00 GMT"
        assert _local(session, "Europe/Berlin") == "15:00 CET"
        assert _local(session, "Asia/Bangkok") == "21:00 UTC+07"

    def test_eu_change_day_itself(self, schedule):
        assert _local(_first_on(schedule, date(2026, 10, 25)), "Europe/London") == "14:00 GMT"

    def test_november_differs_from_landing_page_in_asia(self, schedule):
        session = _first_on(schedule, date(2026, 11, 7))
        assert _local(session, "America/Los_Angeles") == "07:00 PST"
        assert _local(session, "America/New_York") == "10:00 EST"
        assert _local(session, "Europe/London") == "15:00 GMT"
        assert _local(session, "Europe/Berlin") == "16:00 CET"
        assert _local(session, "Asia/Bangkok") == "22:00 UTC+07"  # the page says 9 pm

    def test_us_change_day_session_is_after_the_switch(self, schedule):
        session = _first_on(schedule, date(2026, 11, 1))
        assert _local(session, "America/Los_Angeles") == "07:00 PST"
        assert session.start.astimezone(UTC).hour == 15

    def test_wall_time_inside_dst_gap_is_normalised(self):
        # 02:30 does not exist in Los Angeles on 14 March 2027
        gap = RecurringSchedule(weekdays=[6], start_time="02:30", duration_minutes=45, timezone="America/Los_Angeles")
        session = upcoming_sessions(gap, datetime(2027, 3, 13, tzinfo=LA), 1)[0]
        assert session.start.date() == date(2027, 3, 14)
        assert f"{session.start:%H:%M %Z}" == "03:30 PDT"
        assert (session.end - session.start).total_seconds() == 45 * 60


class TestLabels:
    def test_label_format(self, schedule):
        assert _first_on(schedule, date(2026, 11, 7)).label() == "Sat 7 Nov 2026, 07:00-07:45 PST"

    def test_offset_only_zone_gets_utc_prefix(self):
        assert timezone_abbreviation(datetime(2026, 11, 7, 22, 0, tzinfo=ZoneInfo("Asia/Bangkok"))) == "UTC+07"

    def test_named_zone_keeps_its_abbreviation(self):
        assert timezone_abbreviation(datetime(2026, 11, 7, 7, 0, tzinfo=LA)) == "PST"
