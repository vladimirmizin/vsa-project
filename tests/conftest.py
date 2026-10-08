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
from vsa_commerce.tools import CallContext, CommerceTools
from vsa_commerce.tracking import InMemoryEventLog


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
def events() -> InMemoryEventLog:
    return InMemoryEventLog()


@pytest.fixture
def tools(store: CatalogStore, events: InMemoryEventLog, now: datetime) -> CommerceTools:
    return CommerceTools(store, "victory-skating", events=events, clock=lambda: now)


@pytest.fixture
def ctx() -> CallContext:
    return CallContext(session_id="session-1", channel="test")


@pytest.fixture
def vsa_source_data() -> dict[str, Any]:
    """Snapshot before owner rules."""
    return json.loads((DATA_DIR / "victory-skating" / "catalog.json").read_text(encoding="utf-8"))
