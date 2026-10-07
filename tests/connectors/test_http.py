from __future__ import annotations

import httpx
import pytest

from vsa_commerce.connectors.http import fetch_document
from vsa_commerce.errors import SourceUnavailableError

URL = "https://example.com/page"


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_returns_body_type_and_fetch_time():
    headers = {"content-type": "text/html; charset=utf-8"}
    client = _client(lambda r: httpx.Response(200, text="<p>hi</p>", headers=headers))
    document = fetch_document(URL, client)
    assert document.url == URL
    assert document.body == "<p>hi</p>"
    assert document.content_type == "text/html"
    assert document.fetched_at.tzinfo is not None


def test_sends_browser_compatible_headers():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    fetch_document(URL, _client(handler))
    assert "Mozilla/5.0" in seen[0].headers["user-agent"]
    assert "vsa-commerce-connector" in seen[0].headers["user-agent"]


@pytest.mark.parametrize("status", [403, 404, 500])
def test_non_200_is_source_unavailable(status):
    with pytest.raises(SourceUnavailableError, match=f"HTTP {status}"):
        fetch_document(URL, _client(lambda r: httpx.Response(status)))


def test_network_error_is_source_unavailable():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(SourceUnavailableError, match="no route to host"):
        fetch_document(URL, _client(boom))


def test_creates_and_closes_its_own_client_when_none_given(monkeypatch):
    created: list[httpx.Client] = []
    real_client = httpx.Client

    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")), **kwargs)
        created.append(client)
        return client

    monkeypatch.setattr(httpx, "Client", factory)
    assert fetch_document(URL).body == "ok"
    assert created[0].is_closed
