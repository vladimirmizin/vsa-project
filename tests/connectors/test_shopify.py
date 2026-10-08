from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from tests.support.paths import DATA_DIR, FIXTURES
from vsa_commerce.catalog.store import CatalogStore
from vsa_commerce.connectors.base import SourceConfig
from vsa_commerce.connectors.http import SourceDocument
from vsa_commerce.connectors.registry import PLATFORMS, build_connector, needs_extractor
from vsa_commerce.connectors.shopify import PAGE_SIZE, ShopifyConnector, slugify
from vsa_commerce.domain.models import Catalog, CheckoutMethod, OfferingKind
from vsa_commerce.errors import ExtractionError, SourceUnavailableError
from vsa_commerce.sync.refresh import RefreshStatus, onboard_catalog

FEED = (FIXTURES / "shopify" / "products.json").read_text(encoding="utf-8")
CONFIG = SourceConfig.model_validate_json((DATA_DIR / "edge-skate-shop" / "source.json").read_text(encoding="utf-8"))
NO_FETCH_TIME = {"offerings": {"__all__": {"provenance": {"fetched_at"}}}}


def _client(*pages: str, status: int = 200, seen: list[str] | None = None) -> httpx.Client:
    queue = list(pages)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(str(request.url))
        return httpx.Response(status, text=queue.pop(0) if status == 200 else "")

    return httpx.Client(transport=httpx.MockTransport(handler))


def _offerings(feed: str = FEED, config: SourceConfig = CONFIG) -> dict[str, dict]:
    document = SourceDocument(
        url="https://edge-skate.example.com/products.json", body=feed, fetched_at=datetime(2026, 10, 8, tzinfo=UTC)
    )
    return {o["id"]: o for o in ShopifyConnector(config).extract([document])}


def test_products_become_offerings_and_variants_become_offers():
    spinner = _offerings()["off-ice-spinner-board"]
    assert spinner["kind"] == "product"
    assert spinner["delivery"] == "shipped"
    assert spinner["summary"] == "Practice single, double and triple rotations off the ice."
    assert spinner["enrollment"] == {"mode": "purchase"}
    black, pink = spinner["offers"]
    assert black["name"] == "Off-Ice Spinner Board, Black"
    assert black["price"] == {"amount": "24.99", "currency": "USD"}
    assert black["list_price"] == {"amount": "29.99", "currency": "USD"}
    assert pink["list_price"] is None
    assert (black["available"], pink["available"]) == (True, False)


def test_cart_permalink_carries_attribution():
    assert _offerings()["speed-jump-rope"]["offers"][0]["checkout"] == {
        "method": "cart",
        "url": "https://edge-skate.example.com/cart/4501:1",
        "reference_param": "attributes[ai_session]",
    }


def test_compare_at_equal_to_price_is_not_a_discount():
    rope = _offerings()["speed-jump-rope"]["offers"][0]
    assert rope["name"] == "Speed Jump Rope"
    assert rope["list_price"] is None


def test_machine_tags_are_not_search_goals():
    offerings = _offerings()
    assert offerings["off-ice-spinner-board"]["audience"]["goals"] == ["off-ice spinner", "spin training", "rotation"]
    assert offerings["speed-jump-rope"]["audience"]["goals"] == ["jump rope", "conditioning", "plyometrics"]


def test_output_is_a_valid_catalog():
    catalog = Catalog.model_validate({"business": CONFIG.business, "offerings": list(_offerings().values())})
    assert {o.kind for o in catalog.offerings} == {OfferingKind.PRODUCT}
    assert all(o.offer().checkout.method is CheckoutMethod.CART for o in catalog.offerings)


def test_handles_filter():
    config = CONFIG.model_copy(update={"options": {**CONFIG.options, "handles": ["speed-jump-rope"]}})
    assert list(_offerings(config=config)) == ["speed-jump-rope"]


def test_pagination_stops_on_a_short_page():
    full = json.dumps({"products": [json.loads(FEED)["products"][1]] * PAGE_SIZE})
    seen: list[str] = []
    documents = ShopifyConnector(CONFIG, _client(full, FEED, seen=seen)).fetch()
    assert len(documents) == 2
    assert seen[0].endswith("/products.json?limit=250&page=1")
    assert seen[1].endswith("&page=2")


def test_blocked_store_is_source_unavailable():
    with pytest.raises(SourceUnavailableError, match="HTTP 403"):
        ShopifyConnector(CONFIG, _client(status=403)).fetch()


@pytest.mark.parametrize("body", ["<html>not json</html>", '{"items": []}'])
def test_not_a_products_feed(body):
    with pytest.raises(ExtractionError, match="not a Shopify products feed"):
        _offerings(body)


def test_product_without_variants():
    with pytest.raises(ExtractionError, match="no variants"):
        _offerings(json.dumps({"products": [{"handle": "x", "title": "X", "variants": []}]}))


def test_store_url_is_required():
    with pytest.raises(ValueError, match="store_url"):
        ShopifyConnector(CONFIG.model_copy(update={"options": {}}))


def test_slugify():
    assert slugify("Off-Ice Spinner (Black)!") == "off-ice-spinner-black"


class TestRegistry:
    def test_known_platforms(self):
        assert PLATFORMS == ["shopify", "tilda"]
        assert needs_extractor("tilda")
        assert not needs_extractor("shopify")

    def test_builds_shopify_without_llm(self):
        assert isinstance(build_connector(CONFIG), ShopifyConnector)

    def test_tilda_requires_an_extractor(self):
        with pytest.raises(ValueError, match="LLM extractor"):
            build_connector(SourceConfig(business_id="b", platform="tilda"))

    def test_unknown_platform(self):
        with pytest.raises(ValueError, match="no connector for platform 'mindbody'"):
            build_connector(SourceConfig(business_id="b", platform="mindbody"))


class TestOnboarding:
    def test_committed_catalog_is_what_the_connector_produces(self, tmp_path):
        store = CatalogStore(tmp_path)
        report = onboard_catalog(store, ShopifyConnector(CONFIG, _client(FEED)))
        assert report.status is RefreshStatus.UPDATED
        assert report.changes == ["onboarded 3 offering(s)"]
        fresh = store.load("edge-skate-shop").model_dump(mode="json", exclude=NO_FETCH_TIME)
        committed = CatalogStore(DATA_DIR).load("edge-skate-shop").model_dump(mode="json", exclude=NO_FETCH_TIME)
        assert fresh == committed

    def test_needs_a_business_profile(self, tmp_path):
        config = CONFIG.model_copy(update={"business": None})
        report = onboard_catalog(CatalogStore(tmp_path), ShopifyConnector(config, _client(FEED)))
        assert report.status is RefreshStatus.REJECTED
        assert report.errors == ["source.json has no business profile"]

    def test_source_failure_saves_nothing(self, tmp_path):
        store = CatalogStore(tmp_path)
        report = onboard_catalog(store, ShopifyConnector(CONFIG, _client(status=500)))
        assert report.status is RefreshStatus.REJECTED
        assert store.read_source_snapshot("edge-skate-shop") is None
