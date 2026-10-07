"""File-backed catalog store, one directory per business: catalog.json, owner_rules.json, source.json."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vsa_commerce.domain.models import Catalog
from vsa_commerce.domain.owner_rules import OwnerRules, apply_owner_rules
from vsa_commerce.errors import CatalogNotFoundError

CATALOG_FILE = "catalog.json"
OWNER_RULES_FILE = "owner_rules.json"
SOURCE_CONFIG_FILE = "source.json"
DATA_DIR_ENV = "VSA_DATA_DIR"


def default_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "data"


def build_catalog(raw: dict[str, Any], owner_rules: OwnerRules | None) -> Catalog:
    if owner_rules is not None:
        raw = apply_owner_rules(raw, owner_rules)
    return Catalog.model_validate(raw)


class CatalogStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self._cache: dict[str, Catalog] = {}

    def business_ids(self) -> list[str]:
        if not self.data_dir.is_dir():
            return []
        return sorted(p.name for p in self.data_dir.iterdir() if (p / CATALOG_FILE).is_file())

    def load(self, business_id: str) -> Catalog:
        if business_id not in self._cache:
            raw = self.read_source_snapshot(business_id)
            if raw is None:
                raise CatalogNotFoundError(f"no catalog for business {business_id!r} in {self.data_dir}")
            self._cache[business_id] = build_catalog(raw, self.read_owner_rules(business_id))
        return self._cache[business_id]

    def read_source_snapshot(self, business_id: str) -> dict[str, Any] | None:
        return self._read_json(business_id, CATALOG_FILE)

    def read_owner_rules(self, business_id: str) -> OwnerRules | None:
        raw = self._read_json(business_id, OWNER_RULES_FILE)
        return None if raw is None else OwnerRules.model_validate(raw)

    def read_source_config(self, business_id: str) -> dict[str, Any] | None:
        return self._read_json(business_id, SOURCE_CONFIG_FILE)

    def save_source_snapshot(self, business_id: str, raw: dict[str, Any]) -> Path:
        directory = self.data_dir / business_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / CATALOG_FILE
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)  # atomic replace
        self._cache.pop(business_id, None)
        return path

    def _read_json(self, business_id: str, filename: str) -> dict[str, Any] | None:
        path = self.data_dir / business_id / filename
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a JSON object, got {type(data).__name__}")
        return data
