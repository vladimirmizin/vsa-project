from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from tests.support.fakes import SnapshotExtractor
from tests.support.paths import tilda_html
from vsa_commerce.catalog.store import build_catalog
from vsa_commerce.connectors.base import SourceConfig
from vsa_commerce.connectors.http import SourceDocument
from vsa_commerce.connectors.tilda import TildaConnector, parse_tilda_page
from vsa_commerce.domain.models import EnrollmentMode
from vsa_commerce.errors import SourceUnavailableError
from vsa_commerce.sync.refresh import merge_snapshot

PAGES = {
    "doublejumps": "double-jumps-club",
    "doubleaxel": "double-axel-club",
    "triplejumps": "triple-jumps-club",
}
FETCHED_AT = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


@pytest.fixture
def config() -> SourceConfig:
    return SourceConfig(
        business_id="victory-skating",
        platform="tilda",
        pages=[{"url": f"https://victoryskating.com/{slug}", "offering_id": oid} for slug, oid in PAGES.items()],
    )


@pytest.fixture
def documents(config) -> list[SourceDocument]:
    return [
        SourceDocument(url=str(p.url), body=tilda_html(str(p.url).rsplit("/", 1)[1]), fetched_at=FETCHED_AT)
        for p in config.pages
    ]


def _site(status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, text=tilda_html(request.url.path.strip("/")))

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestParse:
    @pytest.mark.parametrize("slug", PAGES)
    def test_site_chrome_is_removed(self, slug):
        text = parse_tilda_page(tilda_html(slug)).text
        for chrome in ("Cookies managing", "Please enter a valid email", "Download VSA App", "Terms of Service"):
            assert chrome not in text

    def test_product_content_is_kept(self):
        text = parse_tilda_page(tilda_html("doubleaxel")).text
        for fact in ("$299/6 months", "48 Live Group Classes", "Coach Marta", "7 - 7.45 am PDT", "Sneakers"):
            assert fact in text

    def test_page_is_much_smaller_than_html(self):
        html = tilda_html("doubleaxel")
        assert len(parse_tilda_page(html).text) < len(html) / 20

    def test_no_duplicate_blocks(self):
        blocks = parse_tilda_page(tilda_html("doubleaxel")).blocks
        assert len(blocks) == len(set(blocks))

    @pytest.mark.parametrize("slug", PAGES)
    def test_payment_link_matches_catalog(self, slug, vsa):
        expected = str(vsa.get(PAGES[slug]).offer().checkout.url)
        assert parse_tilda_page(tilda_html(slug)).payment_links == [expected]

    @pytest.mark.parametrize("slug", PAGES)
    def test_advertised_start_date(self, slug):
        assert parse_tilda_page(tilda_html(slug)).advertised_start == "Join us on October 10"

    def test_title(self):
        assert parse_tilda_page(tilda_html("doubleaxel")).title == "6-Month Double Axel Club"

    def test_minimal_page(self):
        html = """<html><head><title>Spring camp</title></head><body>
            <div class="t-rec" data-record-type="972">We use cookies</div>
            <div class="t-rec" data-record-type="60">Starts on March 3, 2027.
              <a href="mailto:hi@example.com?subject=hello">mail</a>
              <a href="https://checkout.stripe.com/c/pay/abc">Pay</a>
              <a href="https://checkout.stripe.com/c/pay/abc">Pay again</a></div></body></html>"""
        page = parse_tilda_page(html)
        assert page.title == "Spring camp"
        assert page.text.startswith("Starts on March 3, 2027.")
        assert "cookies" not in page.text
        assert page.advertised_start == "Starts on March 3, 2027"
        assert page.emails == ["hi@example.com"]
        assert page.payment_links == ["https://checkout.stripe.com/c/pay/abc"]

    def test_page_without_title_or_start_date(self):
        page = parse_tilda_page('<div class="t-rec" data-record-type="60">Hello</div>')
        assert page.title == ""
        assert page.advertised_start is None


class TestFetch:
    def test_fetches_every_configured_page(self, config, vsa_source_data):
        connector = TildaConnector(config, SnapshotExtractor(vsa_source_data), http=_site())
        assert [d.url for d in connector.fetch()] == [str(p.url) for p in config.pages]

    def test_blocked_site_is_source_unavailable(self, config, vsa_source_data):
        connector = TildaConnector(config, SnapshotExtractor(vsa_source_data), http=_site(403))
        with pytest.raises(SourceUnavailableError, match="HTTP 403"):
            connector.fetch()

    def test_wrong_platform_rejected(self, config, vsa_source_data):
        with pytest.raises(ValueError, match="cannot handle platform 'shopify'"):
            TildaConnector(config.model_copy(update={"platform": "shopify"}), SnapshotExtractor(vsa_source_data))


class TestExtract:
    def test_extractor_receives_clean_text_and_payment_links(self, config, vsa_source_data, documents):
        extractor = SnapshotExtractor(vsa_source_data)
        TildaConnector(config, extractor).extract(documents)
        request = extractor.requests[1]
        assert request.offering_id == "double-axel-club"
        assert request.fetched_on.isoformat() == "2026-10-08"
        assert request.payment_links == ["https://buy.stripe.com/14AeVd6anbti69kcJ9dMM1M"]
        assert "Cookies" not in request.page_text
        assert request.known_offering_ids == list(PAGES.values())

    def test_connector_owns_identity_and_provenance(self, config, vsa_source_data, documents):
        axel = TildaConnector(config, SnapshotExtractor(vsa_source_data)).extract(documents)[1]
        assert axel["id"] == "double-axel-club"
        assert axel["business_id"] == "victory-skating"
        assert axel["provenance"]["platform"] == "tilda"
        assert axel["provenance"]["fetched_at"] == "2026-10-08T09:00:00+00:00"
        assert axel["provenance"]["advertised"]["start_date"] == "Join us on October 10"
        assert axel["offers"][0]["checkout"]["reference_param"] == "client_reference_id"

    def test_output_builds_a_valid_catalog(self, config, vsa_source_data, documents, store):
        offerings = TildaConnector(config, SnapshotExtractor(vsa_source_data)).extract(documents)
        catalog = build_catalog(merge_snapshot(vsa_source_data, offerings), store.read_owner_rules("victory-skating"))
        assert catalog.get("double-axel-club").enrollment.mode is EnrollmentMode.ROLLING
        assert len(catalog.offerings) == 4
