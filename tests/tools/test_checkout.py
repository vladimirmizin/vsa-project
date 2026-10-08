from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from vsa_commerce.domain.models import Checkout, CheckoutMethod
from vsa_commerce.tools.checkout import build_checkout_url, reference_for

STRIPE = Checkout(
    method=CheckoutMethod.PAYMENT_LINK, url="https://buy.stripe.com/abc", reference_param="client_reference_id"
)


def test_existing_query_parameters_are_kept():
    checkout = STRIPE.model_copy(update={"url": "https://buy.stripe.com/abc?locale=en"})
    url, _ = build_checkout_url(checkout, session_id="s1")
    assert parse_qs(urlsplit(url).query) == {"locale": ["en"], "client_reference_id": ["s1"]}


def test_no_session_means_no_reference():
    url, reference = build_checkout_url(STRIPE, session_id=None)
    assert url == "https://buy.stripe.com/abc"
    assert reference is None


def test_provider_without_reference_support():
    cart = Checkout(method=CheckoutMethod.CART, url="https://shop.example.com/cart/1:1")
    url, reference = build_checkout_url(cart, session_id="s1", email="a@b.co")
    assert url == "https://shop.example.com/cart/1:1"
    assert reference is None


def test_reference_is_stripe_safe_and_bounded():
    assert reference_for("abc-DEF_123") == "abc-DEF_123"
    assert reference_for("a:b c") == "a-b-c"
    assert len(reference_for("x" * 500)) == 200
