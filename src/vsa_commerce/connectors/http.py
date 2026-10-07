from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from vsa_commerce.errors import SourceUnavailableError

# Tilda answers 403 to non-browser user agents
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36 vsa-commerce-connector/0.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


@dataclass(frozen=True, slots=True)
class SourceDocument:
    url: str
    body: str
    fetched_at: datetime
    content_type: str = "text/html"
    meta: dict[str, Any] = field(default_factory=dict)


def fetch_document(url: str, client: httpx.Client | None = None) -> SourceDocument:
    owned = client is None
    http = client or httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True)
    try:
        response = http.get(url, headers=DEFAULT_HEADERS)
    except httpx.HTTPError as exc:
        raise SourceUnavailableError(f"{url}: {exc}") from exc
    finally:
        if owned:
            http.close()
    if response.status_code != httpx.codes.OK:
        raise SourceUnavailableError(f"{url}: HTTP {response.status_code}")
    return SourceDocument(
        url=url,
        body=response.text,
        fetched_at=datetime.now(UTC),
        content_type=response.headers.get("content-type", "text/html").split(";")[0].strip(),
    )
