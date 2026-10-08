from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, HttpUrl, field_validator, model_validator

from vsa_commerce.domain.models.base import CurrencyCode, Model, NonEmptyStr, Slug


class PriceUnit(StrEnum):
    PACKAGE = "package"
    SESSION = "session"
    HOUR = "hour"
    ITEM = "item"


class CheckoutMethod(StrEnum):
    PAYMENT_LINK = "payment_link"
    BOOKING_PAGE = "booking_page"
    CART = "cart"
    IN_APP = "in_app"
    CONTACT = "contact"


class BillingInterval(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class Recurrence(Model):
    interval: BillingInterval
    interval_count: Annotated[int, Field(gt=0)] = 1
    auto_renews: bool = True
    cancellation_policy: str | None = None

    def describe(self) -> str:
        unit = self.interval.value
        return f"every {unit}" if self.interval_count == 1 else f"every {self.interval_count} {unit}s"


class Money(Model):
    amount: Annotated[Decimal, Field(ge=0, decimal_places=2)]
    currency: CurrencyCode = "USD"

    @field_validator("amount")
    @classmethod
    def _cents(cls, value: Decimal) -> Decimal:
        # 299 and 299.00 are the same price and must compare and serialize the same way
        return value.quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"


class Checkout(Model):
    method: CheckoutMethod
    url: HttpUrl | None = None
    label: str | None = None
    reference_param: str | None = Field(
        default=None,
        description="Query parameter passed through to the payment record, e.g. Stripe 'client_reference_id'.",
    )

    @model_validator(mode="after")
    def _url_required_for_self_service(self) -> Self:
        if self.method is not CheckoutMethod.CONTACT and self.url is None:
            raise ValueError(f"checkout method {self.method.value!r} requires a url")
        return self


class Offer(Model):
    id: Slug
    name: NonEmptyStr
    price: Money
    list_price: Money | None = Field(default=None, description="Pre-discount price, if shown.")
    unit: PriceUnit
    duration_months: Annotated[int, Field(gt=0)] | None = None
    sessions_included: Annotated[int, Field(gt=0)] | None = None
    recurring: Recurrence | None = Field(default=None, description="Billing cycle; null for a one-time payment.")
    refundable: bool | None = None
    checkout: Checkout
    terms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent_list_price(self) -> Self:
        if self.list_price is not None:
            if self.list_price.currency != self.price.currency:
                raise ValueError("list_price and price must use the same currency")
            if self.list_price.amount < self.price.amount:
                raise ValueError("list_price cannot be lower than price")
        return self

    # Plain properties, not computed fields: a dumped catalog must validate again unchanged.

    @property
    def discount_percent(self) -> int | None:
        if self.list_price is None or self.list_price.amount == 0:
            return None
        saved = 1 - self.price.amount / self.list_price.amount
        return int((saved * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @property
    def price_per_session(self) -> Money | None:
        if not self.sessions_included:
            return None
        per = (self.price.amount / self.sessions_included).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Money(amount=per, currency=self.price.currency)
