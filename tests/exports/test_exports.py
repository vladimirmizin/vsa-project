from __future__ import annotations

import json

import httpx
import pytest

from vsa_commerce.channels.mcp_server import build_server
from vsa_commerce.domain.models import Catalog
from vsa_commerce.exports import offering_jsonld, render_feed, render_llms_txt, script_tag
from vsa_commerce.exports.cli import export_business, main


@pytest.fixture
def shop(store) -> Catalog:
    return store.load("edge-skate-shop")


class TestJsonLd:
    def test_course_with_weekly_schedule_and_subscription_offer(self, vsa):
        data = offering_jsonld(vsa, vsa.get("double-axel-club"))
        assert data["@type"] == "Course"
        assert data["provider"]["alternateName"] == ["Victory Skating", "VSA", "VSA World"]
        assert data["educationalLevel"] == "Level 3"
        schedule = data["hasCourseInstance"]["courseSchedule"]
        assert schedule["byDay"] == ["https://schema.org/Saturday", "https://schema.org/Sunday"]
        assert (schedule["startTime"], schedule["endTime"]) == ("07:00", "07:45")
        assert schedule["scheduleTimezone"] == "America/Los_Angeles"
        assert "startDate" not in schedule  # rolling enrollment: no single start date
        assert data["hasCourseInstance"]["instructor"][0]["name"] == "Coach Marta"
        offer = data["offers"][0]
        assert (offer["price"], offer["priceCurrency"]) == ("299.00", "USD")
        assert offer["url"] == "https://buy.stripe.com/14AeVd6anbti69kcJ9dMM1M"
        assert offer["priceSpecification"]["billingDuration"] == "P6M"
        assert offer["priceSpecification"]["referencePrice"]["price"] == "699.00"
        assert offer["hasMerchantReturnPolicy"]["returnPolicyCategory"].endswith("MerchantReturnNotPermitted")

    def test_only_social_profiles_are_same_as(self, vsa):
        same_as = offering_jsonld(vsa, vsa.get("double-axel-club"))["provider"]["sameAs"]
        assert same_as == ["https://www.instagram.com/vsaworld", "https://www.instagram.com/vsafigureskating/"]

    def test_cohort_course_gets_a_start_date(self, vsa_source_data):
        literal = Catalog.model_validate(vsa_source_data)
        schedule = offering_jsonld(literal, literal.get("double-axel-club"))["hasCourseInstance"]["courseSchedule"]
        assert schedule["startDate"] == "2026-10-10"

    def test_service(self, vsa):
        data = offering_jsonld(vsa, vsa.get("private-lesson-marta"))
        assert data["@type"] == "Service"
        assert data["offers"][0]["url"] == "https://vsaworld.com/download/"

    def test_product_with_stock(self, shop):
        data = offering_jsonld(shop, shop.get("off-ice-spinner-board"))
        assert data["@type"] == "Product"
        assert data["brand"]["name"] == "Edge Skate Shop"
        assert [o["availability"] for o in data["offers"]] == [
            "https://schema.org/InStock",
            "https://schema.org/OutOfStock",
        ]
        assert "priceSpecification" in data["offers"][0]
        assert "billingDuration" not in data["offers"][0]["priceSpecification"]

    def test_script_tag_is_safe_to_paste(self):
        tag = script_tag({"name": "</script><b>"})
        assert tag.startswith('<script type="application/ld+json">')
        assert "</script><b>" not in tag
        assert json.loads(tag.split("\n", 1)[1].rsplit("</script>", 1)[0]) == {"name": "</script><b>"}


class TestLlmsTxt:
    def test_brief_for_language_models(self, vsa):
        text = render_llms_txt(vsa)
        assert text.startswith("# Victory Skating Academy\n")
        assert "Also known as: Victory Skating, VSA" in text
        assert "- Price: 299.00 USD every 6 months, renews automatically until cancelled, non-refundable" in text
        assert "- Enrollment: open continuously; join any time and start at the next session" in text
        assert "every Saturday and Sunday at 07:00 America/Los_Angeles time" in text
        assert "For AI assistants" not in text

    def test_points_to_the_active_channel(self, vsa):
        text = render_llms_txt(vsa, mcp_url="https://x/mcp", feed_url="https://x/feed.json")
        assert "MCP server with search, details, availability and checkout tools: https://x/mcp" in text


def test_feed_adds_derived_values(vsa, now):
    feed = render_feed(vsa, now=now)
    assert feed["version"] == "1"
    offer = next(o for o in feed["offerings"] if o["id"] == "double-axel-club")["offers"][0]
    assert offer["price_per_session"] == {"amount": "6.23", "currency": "USD"}
    assert offer["discount_percent"] == 57


def test_export_writes_every_artifact(store, tmp_path, now, capsys):
    written = export_business(store, "victory-skating", tmp_path, now=now, base_url=None)
    names = sorted(p.relative_to(tmp_path).as_posix() for p in written)
    assert names[:2] == ["feed.json", "jsonld/double-axel-club.html"]
    assert "llms.txt" in names
    assert len(names) == 2 + 2 * 4
    main(["--out", str(tmp_path / "cli")])
    assert "llms.txt" in capsys.readouterr().out


async def test_served_over_http_next_to_mcp(tools):
    app = build_server(tools).http_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://commerce.test") as client:
        llms = await client.get("/llms.txt")
        feed = await client.get("/feed.json")
        jsonld = await client.get("/jsonld/double-axel-club")
        missing = await client.get("/jsonld/quad-club")
    assert llms.status_code == 200
    assert "http://commerce.test/mcp" in llms.text
    assert feed.json()["business"]["id"] == "victory-skating"
    assert jsonld.headers["content-type"].startswith("application/ld+json")
    assert jsonld.json()["@type"] == "Course"
    assert missing.status_code == 404


def test_shop_exports_too(store, tmp_path, now):
    export_business(store, "edge-skate-shop", tmp_path, now=now, base_url=None)
    assert "Edge Skate Shop" in (tmp_path / "llms.txt").read_text(encoding="utf-8")
