from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from tests.support.paths import fixture_catalog
from vsa_commerce.domain.models import (
    Catalog,
    Checkout,
    CheckoutMethod,
    EnrollmentMode,
    EnrollmentPolicy,
    Money,
    Offer,
    OfferingKind,
    PriceUnit,
    RecurringSchedule,
)


def _offer(**overrides: Any) -> Offer:
    data: dict[str, Any] = {
        "id": "pkg",
        "name": "Package",
        "price": {"amount": "299.00"},
        "unit": "package",
        "checkout": {"method": "payment_link", "url": "https://buy.stripe.com/test"},
    }
    return Offer.model_validate(data | overrides)


class TestSchemaIsBusinessAgnostic:
    @pytest.mark.parametrize(
        ("fixture", "kind", "mode", "checkout"),
        [
            ("salon", OfferingKind.SERVICE, EnrollmentMode.APPOINTMENT, CheckoutMethod.BOOKING_PAGE),
            ("shop", OfferingKind.PRODUCT, EnrollmentMode.PURCHASE, CheckoutMethod.CART),
        ],
    )
    def test_other_business_types_validate(self, fixture, kind, mode, checkout):
        offering = Catalog.model_validate(fixture_catalog(fixture)).offerings[0]
        assert offering.kind is kind
        assert offering.enrollment.mode is mode
        assert offering.offer().checkout.method is checkout
        assert offering.schedule is None

    def test_vsa_catalog_validates(self, vsa):
        assert {o.kind for o in vsa.offerings} == {OfferingKind.COURSE, OfferingKind.SERVICE}
        assert {"Victory Skating", "VSA"} <= set(vsa.business.brand_names)

    def test_shop_variants_are_separate_offers(self):
        offering = Catalog.model_validate(fixture_catalog("shop")).offerings[0]
        assert [o.id for o in offering.offers] == ["black", "pink"]
        assert offering.offer("pink").list_price is None

    @pytest.mark.parametrize("source", ["vsa", "salon", "shop"])
    def test_dump_and_load_round_trip(self, source, vsa):
        catalog = vsa if source == "vsa" else Catalog.model_validate(fixture_catalog(source))
        assert Catalog.model_validate(catalog.model_dump(mode="json")) == catalog


class TestOffer:
    def test_price_per_session_is_derived(self):
        # the page rounds it to "$6 / Class"
        assert _offer(sessions_included=48).price_per_session == Money(amount=Decimal("6.23"))

    def test_no_sessions_no_price_per_session(self):
        assert _offer().price_per_session is None

    def test_discount_percent_from_list_price(self):
        assert _offer(list_price={"amount": "699.00"}).discount_percent == 57

    def test_no_list_price_means_no_discount(self):
        assert _offer().discount_percent is None

    def test_free_list_price_means_no_discount(self):
        assert _offer(price={"amount": "0.00"}, list_price={"amount": "0.00"}).discount_percent is None

    def test_list_price_below_price_rejected(self):
        with pytest.raises(ValidationError, match="list_price cannot be lower"):
            _offer(list_price={"amount": "100.00"})

    def test_list_price_currency_must_match(self):
        with pytest.raises(ValidationError, match="same currency"):
            _offer(list_price={"amount": "699.00", "currency": "EUR"})

    def test_currency_must_be_iso_code(self):
        with pytest.raises(ValidationError):
            Money(amount=Decimal(1), currency="usd")

    def test_negative_price_rejected(self):
        with pytest.raises(ValidationError):
            Money(amount=Decimal(-1))

    def test_money_str(self):
        assert str(Money(amount=Decimal(299))) == "299.00 USD"

    def test_unit_is_an_enum(self):
        assert _offer().unit is PriceUnit.PACKAGE


class TestCheckout:
    def test_self_service_checkout_needs_url(self):
        with pytest.raises(ValidationError, match="requires a url"):
            Checkout(method=CheckoutMethod.PAYMENT_LINK)

    def test_contact_checkout_needs_no_url(self):
        assert Checkout(method=CheckoutMethod.CONTACT).url is None


class TestScheduleAndEnrollment:
    def test_abbreviation_is_not_a_timezone(self):
        with pytest.raises(ValidationError, match="unknown IANA timezone"):
            RecurringSchedule(weekdays=[5], start_time="07:00", duration_minutes=45, timezone="PDT")

    def test_weekdays_unique(self):
        with pytest.raises(ValidationError, match="unique"):
            RecurringSchedule(weekdays=[5, 5], start_time="07:00", duration_minutes=45, timezone="UTC")

    def test_start_time_must_be_naive(self):
        with pytest.raises(ValidationError, match="must be naive"):
            RecurringSchedule(weekdays=[5], start_time="07:00:00+02:00", duration_minutes=45, timezone="UTC")

    def test_sessions_per_week(self, vsa):
        assert vsa.get("double-axel-club").schedule.sessions_per_week == 2

    def test_cohort_requires_dates(self):
        with pytest.raises(ValidationError, match="at least one cohort_start_date"):
            EnrollmentPolicy(mode=EnrollmentMode.COHORT)

    def test_rolling_rejects_cohort_dates(self):
        with pytest.raises(ValidationError, match="only make sense"):
            EnrollmentPolicy(mode=EnrollmentMode.ROLLING, cohort_start_dates=["2026-10-10"])


class TestCatalogIntegrity:
    @pytest.fixture
    def data(self, vsa_source_data) -> dict[str, Any]:
        return copy.deepcopy(vsa_source_data)

    def test_unknown_field_is_an_error(self, data):
        data["offerings"][0]["prise"] = 299
        with pytest.raises(ValidationError, match="prise"):
            Catalog.model_validate(data)

    def test_related_offering_must_exist(self, data):
        data["offerings"][0]["related"] = [{"offering_id": "ghost-club", "relation": "next_step"}]
        with pytest.raises(ValidationError, match="unknown offering 'ghost-club'"):
            Catalog.model_validate(data)

    def test_offering_cannot_relate_to_itself(self, data):
        data["offerings"][0]["related"] = [{"offering_id": data["offerings"][0]["id"], "relation": "next_step"}]
        with pytest.raises(ValidationError, match="cannot relate to itself"):
            Catalog.model_validate(data)

    def test_offering_must_belong_to_business(self, data):
        data["offerings"][0]["business_id"] = "someone-else"
        with pytest.raises(ValidationError, match="belongs to 'someone-else'"):
            Catalog.model_validate(data)

    def test_duplicate_offering_ids_rejected(self, data):
        data["offerings"].append(copy.deepcopy(data["offerings"][0]))
        with pytest.raises(ValidationError, match="duplicate offering ids"):
            Catalog.model_validate(data)

    def test_duplicate_offer_ids_rejected(self, data):
        offers = data["offerings"][0]["offers"]
        offers.append(copy.deepcopy(offers[0]))
        with pytest.raises(ValidationError, match="duplicate offer ids"):
            Catalog.model_validate(data)

    def test_bad_contact_email_rejected(self, data):
        data["business"]["contact_email"] = "not-an-email"
        with pytest.raises(ValidationError, match="contact_email"):
            Catalog.model_validate(data)

    def test_get_unknown_offering_raises_key_error(self, vsa):
        with pytest.raises(KeyError):
            vsa.get("ghost-club")

    def test_get_unknown_offer_raises_key_error(self, vsa):
        with pytest.raises(KeyError):
            vsa.get("double-axel-club").offer("monthly")
