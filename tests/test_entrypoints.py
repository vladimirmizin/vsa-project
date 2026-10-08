from __future__ import annotations

import pytest

from tests.support.paths import DATA_DIR
from vsa_commerce.channels import mcp_server
from vsa_commerce.sync import cli as refresh_cli
from vsa_commerce.tracking import Event, EventType, JsonlEventLog
from vsa_commerce.tracking import cli as report_cli


def test_report_prints_the_funnel(tmp_path, capsys):
    log = JsonlEventLog(tmp_path / "events.jsonl")
    for type_ in (EventType.SEARCH, EventType.CHECKOUT_CREATED):
        log.append(
            Event(
                business_id="victory-skating",
                session_id="s1",
                channel="deepseek",
                type=type_,
                offering_id="double-axel-club",
            )
        )
    report_cli.main(["--events", str(log.path)])
    out = capsys.readouterr().out
    assert "victory-skating: 1 AI session(s)" in out
    assert "checkout_created" in out
    assert "{'deepseek': 1}" in out


def test_report_as_json(tmp_path, capsys):
    report_cli.main(["--events", str(tmp_path / "none.jsonl"), "--json"])
    assert '"sessions": 0' in capsys.readouterr().out


def test_refresh_needs_an_api_key(monkeypatch):
    monkeypatch.setattr(refresh_cli, "load_dotenv", lambda *_: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="DEEPSEEK_API_KEY"):
        refresh_cli.main(["--data-dir", str(DATA_DIR)])


def test_refresh_unknown_business(tmp_path):
    with pytest.raises(SystemExit, match=r"no source.json"):
        refresh_cli.main(["--business", "ghost", "--data-dir", str(tmp_path)])


@pytest.mark.parametrize(
    ("argv", "expected"), [([], {}), (["--transport", "http", "--port", "9000"], {"transport": "http", "port": 9000})]
)
def test_mcp_server_main(monkeypatch, tmp_path, argv, expected):
    calls: list[dict] = []
    monkeypatch.setattr(mcp_server.FastMCP, "run", lambda self, **kwargs: calls.append(kwargs))
    mcp_server.main(["--data-dir", str(DATA_DIR), "--events", str(tmp_path / "e.jsonl"), *argv])
    assert calls == [{**expected, "show_banner": False}]
