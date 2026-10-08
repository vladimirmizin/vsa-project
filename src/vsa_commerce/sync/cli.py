"""``vsa-refresh``: re-read a business's source and update its catalog snapshot."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from vsa_commerce.catalog.store import CatalogStore, default_data_dir
from vsa_commerce.channels.llm import LLMSettings, MissingApiKeyError, OpenAICompatibleChat
from vsa_commerce.connectors.base import SourceConfig
from vsa_commerce.connectors.tilda import TildaConnector
from vsa_commerce.extraction import LLMOfferingExtractor
from vsa_commerce.sync.refresh import refresh_catalog


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    load_dotenv(default_data_dir().parent / ".env")
    parser = argparse.ArgumentParser(description="Refresh a catalog snapshot from its source.")
    parser.add_argument("--business", default="victory-skating")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="show the diff without saving")
    parser.add_argument("--approve", action="store_true", help="publish changes to prices, checkout or schedule")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")

    store = CatalogStore(args.data_dir or default_data_dir())
    raw_config = store.read_source_config(args.business)
    if raw_config is None:
        sys.exit(f"no source.json for {args.business!r}")
    config = SourceConfig.model_validate(raw_config)
    if config.platform != TildaConnector.platform:
        sys.exit(f"no connector registered for platform {config.platform!r}")
    try:
        chat = OpenAICompatibleChat(LLMSettings.from_env())
    except MissingApiKeyError as exc:
        sys.exit(str(exc))

    connector = TildaConnector(config, LLMOfferingExtractor(chat))
    report = refresh_catalog(store, connector, dry_run=args.dry_run, approve=args.approve)
    print(f"{report.business_id}: {report.status.value}" + (" (saved)" if report.saved else ""))
    for line in report.changes + [f"error: {e}" for e in report.errors]:
        print(f"  {line}")
    if report.needs_review:
        print(f"\n{len(report.needs_review)} change(s) affect what customers pay or when they attend:")
        for line in report.needs_review:
            print(f"  ! {line}")
        print("Review them, then run again with --approve to publish.")
    sys.exit(1 if report.kept_previous_snapshot else 0)


if __name__ == "__main__":
    main()
