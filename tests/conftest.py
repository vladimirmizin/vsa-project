from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from tests.support.paths import DATA_DIR, NOW
from vsa_commerce.catalog.store import CatalogStore
from vsa_commerce.domain.models import Catalog


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def store() -> CatalogStore:
    return CatalogStore(DATA_DIR)


@pytest.fixture
def tmp_store(tmp_path: Path) -> CatalogStore:
    shutil.copytree(DATA_DIR / "victory-skating", tmp_path / "victory-skating")
    return CatalogStore(tmp_path)


@pytest.fixture
def vsa(store: CatalogStore) -> Catalog:
    return store.load("victory-skating")


@pytest.fixture
def vsa_source_data() -> dict[str, Any]:
    """Snapshot before owner rules."""
    return json.loads((DATA_DIR / "victory-skating" / "catalog.json").read_text(encoding="utf-8"))
