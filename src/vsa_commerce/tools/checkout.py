from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from vsa_commerce.domain.models import Checkout, CheckoutMethod

# Stripe accepts letters, digits, '-' and '_' in client_reference_id, up to 200 characters
_REFERENCE_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
_PREFILLED_EMAIL = {"buy.stripe.com": "prefilled_email"}


def reference_for(session_id: str) -> str:
    return _REFERENCE_UNSAFE.sub("-", session_id)[:200]


def build_checkout_url(
    checkout: Checkout, *, session_id: str | None, email: str | None = None
) -> tuple[str, str | None]:
    """The checkout URL with attribution (and an optional prefilled email) where the provider supports it."""
    url = str(checkout.url)
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query))
    reference = None
    if checkout.method is CheckoutMethod.PAYMENT_LINK and checkout.reference_param and session_id:
        reference = reference_for(session_id)
        params[checkout.reference_param] = reference
    email_param = _PREFILLED_EMAIL.get(parts.netloc)
    if email and email_param:
        params[email_param] = email
    return urlunsplit(parts._replace(query=urlencode(params))), reference
