"""Shopify storefronts via the public ``/products.json``. Structured data, so no LLM is involved."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

import httpx
from bs4 import BeautifulSoup

from vsa_commerce.connectors.base import SourceConfig, SourceConnector
from vsa_commerce.connectors.http import SourceDocument, fetch_document
from vsa_commerce.errors import ExtractionError

PAGE_SIZE = 250
MAX_PAGES = 20
# Cart permalink attributes are stored on the order, which lets a paid order be traced to the AI session
REFERENCE_PARAM = "attributes[ai_session]"
_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return _SLUG_UNSAFE.sub("-", text.lower()).strip("-")[:64].strip("-")


class ShopifyConnector(SourceConnector):
    platform = "shopify"

    def __init__(self, config: SourceConfig, http: httpx.Client | None = None) -> None:
        super().__init__(config, http)
        store_url = config.options.get("store_url")
        if not store_url:
            raise ValueError("shopify source needs options.store_url")
        self.store_url = str(store_url).rstrip("/")
        self.currency = str(config.options.get("currency", "USD"))
        self.handles: set[str] = set(config.options.get("handles", []))

    def fetch(self) -> list[SourceDocument]:
        documents = []
        for page in range(1, MAX_PAGES + 1):
            document = fetch_document(f"{self.store_url}/products.json?limit={PAGE_SIZE}&page={page}", self.http)
            documents.append(document)
            if len(_products(document)) < PAGE_SIZE:
                break
        return documents

    def extract(self, documents: list[SourceDocument]) -> list[dict[str, Any]]:
        offerings = []
        for document in documents:
            for product in _products(document):
                if self.handles and product.get("handle") not in self.handles:
                    continue
                offerings.append(self._offering(product, document))
        return offerings

    def _offering(self, product: dict[str, Any], document: SourceDocument) -> dict[str, Any]:
        handle = product["handle"]
        description = _text(product.get("body_html") or "")
        variants = product.get("variants") or []
        if not variants:
            raise ExtractionError(f"product {handle!r} has no variants")
        return {
            "id": slugify(handle),
            "business_id": self.config.business_id,
            "kind": "product",
            "name": product["title"],
            "summary": _first_sentence(description) or product["title"],
            "description": description,
            "delivery": "shipped" if any(v.get("requires_shipping", True) for v in variants) else "online",
            "audience": {"goals": _goals(product)},
            "enrollment": {"mode": "purchase"},
            "offers": [self._offer(product["title"], v) for v in variants],
            "provenance": {
                "source_url": f"{self.store_url}/products/{handle}",
                "platform": self.platform,
                "fetched_at": document.fetched_at.isoformat(),
                "advertised": {"vendor": product.get("vendor") or ""},
            },
        }

    def _offer(self, title: str, variant: dict[str, Any]) -> dict[str, Any]:
        price = Decimal(str(variant["price"]))
        compare_at = variant.get("compare_at_price")
        list_price = Decimal(str(compare_at)) if compare_at else None
        variant_title = variant.get("title") or ""
        return {
            "id": f"variant-{variant['id']}",
            "name": title if variant_title in ("", "Default Title") else f"{title}, {variant_title}",
            "price": {"amount": str(price), "currency": self.currency},
            "list_price": (
                {"amount": str(list_price), "currency": self.currency} if list_price and list_price > price else None
            ),
            "unit": "item",
            "available": variant.get("available"),
            "checkout": {
                "method": "cart",
                "url": f"{self.store_url}/cart/{variant['id']}:1",
                "reference_param": REFERENCE_PARAM,
            },
        }


def _products(document: SourceDocument) -> list[dict[str, Any]]:
    try:
        products = json.loads(document.body)["products"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ExtractionError(f"{document.url}: not a Shopify products feed") from exc
    return list(products)


def _text(html: str) -> str:
    return " ".join(BeautifulSoup(html, "html.parser").get_text(" ").split())


def _first_sentence(text: str) -> str:
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    return (match.group(1) if match else text)[:300]


def _goals(product: dict[str, Any]) -> list[str]:
    tags = product.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    # skip machine tags such as "brand::gender => womens"
    words = [product.get("product_type") or "", *[t for t in tags if not re.search(r"::|=>|:", t)]]
    return list(dict.fromkeys(w.strip().lower() for w in words if w and w.strip()))
