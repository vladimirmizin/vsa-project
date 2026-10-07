"""Refresh a catalog snapshot from its source. The live catalog is only replaced by validated data."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from vsa_commerce.catalog.store import CatalogStore, build_catalog
from vsa_commerce.connectors.base import SourceConnector
from vsa_commerce.domain.models import Catalog
from vsa_commerce.errors import ExtractionError, OwnerRuleError, SourceUnavailableError
from vsa_commerce.sync.diff import diff_snapshots

log = logging.getLogger(__name__)


class RefreshStatus(StrEnum):
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    SOURCE_UNAVAILABLE = "source_unavailable"
    REJECTED = "rejected"


@dataclass
class RefreshReport:
    business_id: str
    status: RefreshStatus
    changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    saved: bool = False

    @property
    def kept_previous_snapshot(self) -> bool:
        return self.status in (RefreshStatus.SOURCE_UNAVAILABLE, RefreshStatus.REJECTED)


def refresh_catalog(store: CatalogStore, connector: SourceConnector, *, dry_run: bool = False) -> RefreshReport:
    business_id = connector.config.business_id

    def keep_previous(status: RefreshStatus, error: object) -> RefreshReport:
        log.warning("refresh %s: %s, keeping previous snapshot: %s", business_id, status.value, error)
        return RefreshReport(business_id, status, errors=[str(error)])

    previous = store.read_source_snapshot(business_id)
    if previous is None:
        return keep_previous(RefreshStatus.REJECTED, f"no snapshot for {business_id!r}: onboard the business first")

    try:
        offerings = connector.extract(connector.fetch())
    except SourceUnavailableError as exc:
        return keep_previous(RefreshStatus.SOURCE_UNAVAILABLE, exc)
    except ExtractionError as exc:
        return keep_previous(RefreshStatus.REJECTED, exc)

    candidate = merge_snapshot(previous, offerings)
    try:
        build_catalog(candidate, store.read_owner_rules(business_id))
        changes = diff_snapshots(_normalize(previous), _normalize(candidate))
    except (ValidationError, OwnerRuleError) as exc:
        return keep_previous(RefreshStatus.REJECTED, exc)

    report = RefreshReport(business_id, RefreshStatus.UPDATED if changes else RefreshStatus.UNCHANGED, changes=changes)
    if changes and not dry_run:
        store.save_source_snapshot(business_id, candidate)
        report.saved = True
    log.info("refresh %s: %s, %d change(s), saved=%s", business_id, report.status.value, len(changes), report.saved)
    return report


def merge_snapshot(previous: dict[str, Any], offerings: list[dict[str, Any]]) -> dict[str, Any]:
    """Fresh offerings replace stored ones by id; offerings the connector does not produce are kept."""
    fresh = {o["id"]: o for o in offerings}
    merged = [fresh.pop(o["id"], o) for o in previous.get("offerings", [])]
    merged.extend(fresh.values())
    return {**previous, "offerings": merged}


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    # expanded form, so an explicit default vs an omitted one is not a change
    return Catalog.model_validate(raw).model_dump(mode="json")
