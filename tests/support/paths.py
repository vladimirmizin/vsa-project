from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
FIXTURES = ROOT / "tests" / "fixtures"

# three days before the "Join us on October 10" date on the landing page
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def fixture_catalog(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / "catalogs" / f"{name}.json").read_text(encoding="utf-8"))


def tilda_html(slug: str) -> str:
    return (FIXTURES / "tilda" / f"{slug}.html").read_text(encoding="utf-8")
