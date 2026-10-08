from __future__ import annotations

import json

import pytest

from tests.support.paths import DATA_DIR
from vsa_commerce.catalog.store import DATA_DIR_ENV, CatalogStore, default_data_dir
from vsa_commerce.domain.models import EnrollmentMode
from vsa_commerce.errors import CatalogNotFoundError


def test_lists_businesses(store):
    assert store.business_ids() == ["edge-skate-shop", "victory-skating"]


def test_missing_data_dir_lists_nothing(tmp_path):
    assert CatalogStore(tmp_path / "nope").business_ids() == []


def test_unknown_business(store):
    with pytest.raises(CatalogNotFoundError, match="ghost"):
        store.load("ghost")


def test_load_is_cached(store):
    assert store.load("victory-skating") is store.load("victory-skating")


def test_owner_rules_applied_on_load(store):
    assert store.load("victory-skating").get("double-axel-club").enrollment.mode is EnrollmentMode.ROLLING


def test_works_without_owner_rules(tmp_store):
    (tmp_store.data_dir / "victory-skating" / "owner_rules.json").unlink()
    assert tmp_store.read_owner_rules("victory-skating") is None
    assert tmp_store.load("victory-skating").get("double-axel-club").enrollment.mode is EnrollmentMode.COHORT


def test_source_config_is_readable(store):
    config = store.read_source_config("victory-skating")
    assert config is not None
    assert config["platform"] == "tilda"


def test_saving_a_new_snapshot_keeps_owner_rules(tmp_store, vsa_source_data):
    tmp_store.load("victory-skating")
    vsa_source_data["offerings"][1]["name"] = "Double Axel Club (renamed on the site)"
    tmp_store.save_source_snapshot("victory-skating", vsa_source_data)

    reloaded = tmp_store.load("victory-skating").get("double-axel-club")
    assert reloaded.name == "Double Axel Club (renamed on the site)"
    assert reloaded.enrollment.mode is EnrollmentMode.ROLLING


def test_snapshot_is_written_as_utf8_without_leftovers(tmp_store, vsa_source_data):
    path = tmp_store.save_source_snapshot("victory-skating", vsa_source_data)
    assert "Toruń" in path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == vsa_source_data
    assert not list(path.parent.glob("*.tmp"))


def test_file_that_is_not_an_object_is_rejected(tmp_store):
    (tmp_store.data_dir / "victory-skating" / "catalog.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a JSON object, got list"):
        tmp_store.load("victory-skating")


def test_data_dir_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path))
    assert default_data_dir() == tmp_path


def test_default_data_dir_is_repo_data(monkeypatch):
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    assert default_data_dir() == DATA_DIR
