"""``vsa-export``: write llms.txt, the JSON feed and JSON-LD snippets for one business."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from vsa_commerce.catalog.store import CatalogStore, default_data_dir
from vsa_commerce.exports import offering_jsonld, render_feed, render_llms_txt, script_tag


def export_business(
    store: CatalogStore, business_id: str, out: Path, *, now: datetime, base_url: str | None
) -> list[Path]:
    catalog = store.load(business_id)
    out.mkdir(parents=True, exist_ok=True)
    written = []

    def write(name: str, text: str) -> None:
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)

    feed_url = f"{base_url}/feed.json" if base_url else None
    mcp_url = f"{base_url}/mcp" if base_url else None
    write("llms.txt", render_llms_txt(catalog, mcp_url=mcp_url, feed_url=feed_url))
    write("feed.json", json.dumps(render_feed(catalog, now=now), ensure_ascii=False, indent=2) + "\n")
    for offering in catalog.offerings:
        data = offering_jsonld(catalog, offering)
        write(f"jsonld/{offering.id}.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        write(f"jsonld/{offering.id}.html", script_tag(data))
    return written


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description="Export the passive discovery channel for a business.")
    parser.add_argument("--business", default="victory-skating")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="default: exports/<business>")
    parser.add_argument("--base-url", default=None, help="public URL where the HTTP server is reachable")
    args = parser.parse_args(argv)

    store = CatalogStore(args.data_dir or default_data_dir())
    out = args.out or default_data_dir().parent / "exports" / args.business
    for path in export_business(store, args.business, out, now=datetime.now(UTC), base_url=args.base_url):
        print(path)


if __name__ == "__main__":
    main()
