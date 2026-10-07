"""Tilda landing pages: chrome is dropped by record type, exact facts are read from markup, prose goes to the LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from vsa_commerce.connectors.base import SourceConfig, SourceConnector
from vsa_commerce.connectors.http import SourceDocument, fetch_document
from vsa_commerce.domain.models import ADVERTISED_START_KEY
from vsa_commerce.extraction import ExtractionRequest, OfferingExtractor, assemble_offering

# Site chrome on every Tilda site, not product content
BOILERPLATE_RECORD_TYPES: dict[str, str] = {
    "446": "header menu",
    "978": "submenu",
    "972": "cookie consent banner",
    "718": "contact form",
    "992": "footer",
}

PAYMENT_LINK_HOSTS = ("buy.stripe.com", "checkout.stripe.com", "www.paypal.com", "paypal.me")

_MONTH_DAY = r"[A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?"
START_DATE_PATTERNS = (
    re.compile(rf"Join us on\s+(?:[A-Z][a-z]+day,?\s+)?{_MONTH_DAY}"),
    re.compile(rf"(?:Starts?|Starting|Start date:?)\s+(?:on\s+)?{_MONTH_DAY}"),
)


@dataclass(frozen=True, slots=True)
class TildaPage:
    title: str
    blocks: list[str]
    payment_links: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    advertised_start: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)


def parse_tilda_page(html: str) -> TildaPage:
    soup = BeautifulSoup(html, "html.parser")
    title = " ".join(soup.title.get_text().split()) if soup.title else ""
    payment_links, emails = _links(soup)
    blocks = _content_blocks(soup)
    return TildaPage(
        title=title,
        blocks=blocks,
        payment_links=payment_links,
        emails=emails,
        advertised_start=_advertised_start("\n".join(blocks)),
    )


def _links(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    payment_links: list[str] = []
    emails: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if any(f"//{host}/" in href for host in PAYMENT_LINK_HOSTS) and href not in payment_links:
            payment_links.append(href)
        elif href.startswith("mailto:"):
            address = href.removeprefix("mailto:").split("?")[0]
            if address not in emails:
                emails.append(address)
    return payment_links, emails


def _content_blocks(soup: BeautifulSoup) -> list[str]:
    blocks: list[str] = []
    for record in soup.select("div.t-rec"):
        if not isinstance(record, Tag) or record.get("data-record-type") in BOILERPLATE_RECORD_TYPES:
            continue
        for tag in record(["script", "style", "noscript", "form"]):
            tag.decompose()
        text = " ".join(record.get_text(" ").split())
        # desktop and mobile variants of the same record
        if text and text not in blocks:
            blocks.append(text)
    return blocks


def _advertised_start(text: str) -> str | None:
    for pattern in START_DATE_PATTERNS:
        if match := pattern.search(text):
            return match.group(0)
    return None


class TildaConnector(SourceConnector):
    platform = "tilda"

    def __init__(self, config: SourceConfig, extractor: OfferingExtractor, http: httpx.Client | None = None) -> None:
        super().__init__(config, http)
        self.extractor = extractor

    def fetch(self) -> list[SourceDocument]:
        return [fetch_document(str(page.url), self.http) for page in self.config.pages]

    def extract(self, documents: list[SourceDocument]) -> list[dict[str, Any]]:
        offering_ids = {str(page.url): page.offering_id for page in self.config.pages}
        known_ids = list(offering_ids.values())
        return [self._extract_one(doc, offering_ids[doc.url], known_ids) for doc in documents]

    def _extract_one(self, document: SourceDocument, offering_id: str, known_ids: list[str]) -> dict[str, Any]:
        page = parse_tilda_page(document.body)
        request = ExtractionRequest(
            business_id=self.config.business_id,
            offering_id=offering_id,
            source_url=document.url,
            fetched_on=document.fetched_at.date(),
            page_title=page.title,
            page_text=page.text,
            payment_links=page.payment_links,
            known_offering_ids=known_ids,
        )
        extracted = self.extractor.extract(request)
        if page.advertised_start:
            # exact value from markup wins over the model's
            advertised = {**extracted.advertised, ADVERTISED_START_KEY: page.advertised_start}
            extracted = extracted.model_copy(update={"advertised": advertised})
        return assemble_offering(extracted, request, platform=self.platform, fetched_at=document.fetched_at)
