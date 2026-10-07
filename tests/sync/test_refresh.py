from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.support.fakes import OfferingEdit, SnapshotExtractor
from tests.support.paths import DATA_DIR, tilda_html
from vsa_commerce.catalog.store import CatalogStore
from vsa_commerce.connectors.base import SourceConfig
from vsa_commerce.connectors.tilda import TildaConnector
from vsa_commerce.domain.models import EnrollmentMode
from vsa_commerce.errors import ExtractionError
from vsa_commerce.extraction import ExtractedOffering, ExtractionRequest
from vsa_commerce.sync.refresh import RefreshStatus, refresh_catalog

CONFIG = SourceConfig.model_validate_json((DATA_DIR / "victory-skating" / "source.json").read_text(encoding="utf-8"))
AXEL_PRICE_PATH = "offerings[double-axel-club].offers[six-month-package].price.amount"


def _site(status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, text=tilda_html(request.url.path.strip("/")))

    return httpx.Client(transport=httpx.MockTransport(handler))


def _connector(snapshot: dict[str, Any], edit: OfferingEdit | None = None, *, status: int = 200) -> TildaConnector:
    return TildaConnector(CONFIG, SnapshotExtractor(snapshot, edit), http=_site(status))


def _raise_axel_price(offering_id: str, offering: dict[str, Any]) -> None:
    if offering_id == "double-axel-club":
        offering["offers"][0]["price"]["amount"] = "349.00"


def _axel_price(store: CatalogStore) -> str:
    return str(CatalogStore(store.data_dir).load("victory-skating").get("double-axel-club").offer().price.amount)


def test_same_content_is_unchanged(tmp_store, vsa_source_data):
    path = tmp_store.data_dir / "victory-skating" / "catalog.json"
    before = path.read_text(encoding="utf-8")
    report = refresh_catalog(tmp_store, _connector(vsa_source_data))
    assert report.status is RefreshStatus.UNCHANGED, report.changes
    assert report.saved is False
    assert path.read_text(encoding="utf-8") == before


def test_price_change_is_detected_and_saved(tmp_store, vsa_source_data):
    report = refresh_catalog(tmp_store, _connector(vsa_source_data, _raise_axel_price))
    assert report.status is RefreshStatus.UPDATED
    assert report.saved is True
    assert report.changes == [f"changed {AXEL_PRICE_PATH}: '299.00' -> '349.00'"]
    assert _axel_price(tmp_store) == "349.00"


def test_owner_rules_survive_a_refresh(tmp_store, vsa_source_data):
    refresh_catalog(tmp_store, _connector(vsa_source_data, _raise_axel_price))
    reloaded = CatalogStore(tmp_store.data_dir).load("victory-skating").get("double-axel-club")
    assert reloaded.enrollment.mode is EnrollmentMode.ROLLING


def test_dry_run_reports_but_does_not_save(tmp_store, vsa_source_data):
    report = refresh_catalog(tmp_store, _connector(vsa_source_data, _raise_axel_price), dry_run=True)
    assert report.status is RefreshStatus.UPDATED
    assert report.saved is False
    assert _axel_price(tmp_store) == "299.00"


def test_source_down_keeps_previous_snapshot(tmp_store, vsa_source_data):
    report = refresh_catalog(tmp_store, _connector(vsa_source_data, status=403))
    assert report.status is RefreshStatus.SOURCE_UNAVAILABLE
    assert report.kept_previous_snapshot
    assert "HTTP 403" in report.errors[0]
    assert _axel_price(tmp_store) == "299.00"


def test_extraction_failure_keeps_previous_snapshot(tmp_store):
    class Broken:
        def extract(self, request: ExtractionRequest) -> ExtractedOffering:
            raise ExtractionError("model returned nonsense")

    report = refresh_catalog(tmp_store, TildaConnector(CONFIG, Broken(), http=_site()))
    assert report.status is RefreshStatus.REJECTED
    assert report.kept_previous_snapshot
    assert report.errors == ["model returned nonsense"]


def test_invalid_catalog_is_rejected(tmp_store, vsa_source_data):
    def dangling(offering_id: str, offering: dict[str, Any]) -> None:
        offering["related"] = [{"offering_id": "ghost-club", "relation": "next_step"}]

    report = refresh_catalog(tmp_store, _connector(vsa_source_data, dangling))
    assert report.status is RefreshStatus.REJECTED
    assert "ghost-club" in report.errors[0]
    assert report.saved is False


def test_offerings_not_produced_by_the_connector_are_kept(tmp_store, vsa_source_data):
    refresh_catalog(tmp_store, _connector(vsa_source_data, _raise_axel_price))
    ids = [o.id for o in CatalogStore(tmp_store.data_dir).load("victory-skating").offerings]
    assert "private-lesson-marta" in ids


def test_business_must_be_onboarded_first(tmp_path, vsa_source_data):
    report = refresh_catalog(CatalogStore(tmp_path), _connector(vsa_source_data))
    assert report.status is RefreshStatus.REJECTED
    assert "onboard" in report.errors[0]


@pytest.mark.parametrize("status", [RefreshStatus.SOURCE_UNAVAILABLE, RefreshStatus.REJECTED])
def test_kept_previous_snapshot_flag(status):
    from vsa_commerce.sync.refresh import RefreshReport

    assert RefreshReport("b", status).kept_previous_snapshot
    assert not RefreshReport("b", RefreshStatus.UPDATED).kept_previous_snapshot
