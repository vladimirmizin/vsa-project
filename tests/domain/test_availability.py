"""Free on November 6 -> sessions on 7 and 8 November, despite 'Join us on October 10'."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from tests.support.paths import fixture_catalog
from vsa_commerce.domain.availability import check_availability
from vsa_commerce.domain.models import Catalog, EnrollmentMode

LA = ZoneInfo("America/Los_Angeles")
NOV_6 = date(2026, 11, 6)


@pytest.fixture
def double_axel(vsa):
    return vsa.get("double-axel-club")


@pytest.fixture
def literal_double_axel(vsa_source_data):
    return Catalog.model_validate(vsa_source_data).get("double-axel-club")


class TestTheAssignmentExample:
    def test_free_on_november_6_can_join(self, double_axel, now):
        result = check_availability(double_axel, now=now, requested_date=NOV_6)
        assert result.can_join is True
        assert result.enrollment_mode is EnrollmentMode.ROLLING
        first, second = result.upcoming_sessions[:2]
        assert first.starts_at == datetime(2026, 11, 7, 7, 0, tzinfo=LA)
        assert second.starts_at == datetime(2026, 11, 8, 7, 0, tzinfo=LA)
        assert "First session from the requested time: Sat 7 Nov 2026, 07:00-07:45 PST." in result.notes

    def test_advertised_date_is_explained_not_enforced(self, double_axel, now):
        note = check_availability(double_axel, now=now, requested_date=NOV_6).advertised_start_note
        assert note is not None
        assert "Join us on October 10" in note
        assert "not an enrollment deadline" in note

    def test_same_question_from_bangkok(self, double_axel, now):
        result = check_availability(double_axel, now=now, requested_date=NOV_6, timezone="Asia/Bangkok")
        assert result.timezone == "Asia/Bangkok"
        assert result.upcoming_sessions[0].label == "Sat 7 Nov 2026, 22:00-22:45 UTC+07"

    def test_enroll_by_accounts_for_access_lead_time(self, double_axel, now):
        result = check_availability(double_axel, now=now, requested_date=NOV_6)
        assert result.enroll_by == datetime(2026, 11, 6, 7, 0, tzinfo=LA)

    def test_reading_the_page_literally_gets_it_wrong(self, literal_double_axel, now):
        result = check_availability(literal_double_axel, now=now, requested_date=NOV_6)
        assert result.can_join is False
        assert result.upcoming_sessions == []
        assert result.explanation == "There is no upcoming start date for this offering."


class TestDates:
    def test_before_advertised_start(self, double_axel, now):
        result = check_availability(double_axel, now=now, requested_date=date(2026, 10, 8))
        assert result.upcoming_sessions[0].starts_at.date() == date(2026, 10, 10)

    def test_no_date_means_next_sessions_from_now(self, double_axel, now):
        result = check_availability(double_axel, now=now)
        assert result.requested_date is None
        assert result.upcoming_sessions[0].starts_at == datetime(2026, 10, 10, 7, 0, tzinfo=LA)

    def test_date_in_the_past_does_not_crash(self, double_axel, now):
        result = check_availability(double_axel, now=now, requested_date=date(2026, 9, 1))
        assert result.can_join is True
        assert any("already in the past" in n for n in result.notes)
        assert result.upcoming_sessions[0].starts_at >= now

    def test_far_future_date(self, double_axel, now):
        result = check_availability(double_axel, now=now, requested_date=date(2027, 6, 1))
        assert result.upcoming_sessions[0].starts_at.date() == date(2027, 6, 5)

    def test_first_session_too_soon_for_access_links(self, double_axel):
        friday_noon = datetime(2026, 11, 6, 12, 0, tzinfo=LA)
        result = check_availability(double_axel, now=friday_noon)
        assert result.enroll_by is not None
        assert result.enroll_by < friday_noon
        assert any("may come too soon" in n for n in result.notes)
        assert len(result.upcoming_sessions) == 4

    def test_session_count(self, double_axel, now):
        assert len(check_availability(double_axel, now=now, session_count=2).upcoming_sessions) == 2

    def test_naive_now_rejected(self, double_axel):
        with pytest.raises(ValueError, match="timezone-aware"):
            check_availability(double_axel, now=datetime(2026, 10, 7))  # noqa: DTZ001 - the point of the test


class TestOtherEnrollmentModes:
    def test_cohort_picks_next_start_date(self, literal_double_axel, now):
        result = check_availability(literal_double_axel, now=now, requested_date=date(2026, 10, 8))
        assert result.can_join is True
        assert result.next_cohort_date == date(2026, 10, 10)
        assert "Saturday, 10 October 2026" in result.explanation
        assert result.upcoming_sessions[0].starts_at == datetime(2026, 10, 10, 7, 0, tzinfo=LA)
        assert result.advertised_start_note is None

    def test_cohort_with_past_requested_date(self, literal_double_axel, now):
        result = check_availability(literal_double_axel, now=now, requested_date=date(2026, 9, 1))
        assert any("already in the past" in n for n in result.notes)
        assert result.next_cohort_date == date(2026, 10, 10)

    def test_appointment_has_no_fixed_sessions(self, vsa, now):
        result = check_availability(vsa.get("private-lesson-marta"), now=now)
        assert result.can_join is True
        assert result.enrollment_mode is EnrollmentMode.APPOINTMENT
        assert result.upcoming_sessions == []
        assert result.enroll_by is None
        assert result.timezone == "UTC"

    def test_product_can_always_be_bought(self, now):
        spinner = Catalog.model_validate(fixture_catalog("shop")).offerings[0]
        result = check_availability(spinner, now=now, requested_date=NOV_6)
        assert result.can_join is True
        assert result.explanation == "Can be purchased at any time."
        assert result.notes == []


def test_result_is_json_serialisable(double_axel, now):
    payload = check_availability(double_axel, now=now, requested_date=NOV_6).model_dump(mode="json")
    assert payload["upcoming_sessions"][0]["starts_at"] == "2026-11-07T07:00:00-08:00"
    assert datetime.fromisoformat(payload["enroll_by"]).astimezone(UTC).hour == 15
