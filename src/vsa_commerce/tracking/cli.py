"""``vsa-report``: conversion funnel and sales signals from the event log."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vsa_commerce.catalog.store import default_data_dir
from vsa_commerce.tracking import JsonlEventLog, funnel_report


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description="Show the AI conversion funnel for a business.")
    parser.add_argument("--business", default="victory-skating")
    parser.add_argument("--events", type=Path, default=default_data_dir().parent / "var" / "events.jsonl")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = funnel_report(JsonlEventLog(args.events).read(), args.business)
    if args.json:
        print(report.model_dump_json(indent=2))
        return
    print(f"{report.business_id}: {report.sessions} AI session(s)")
    for step in report.steps:
        rate = f"  ({step.rate_from_previous:.0%} of previous)" if step.rate_from_previous is not None else ""
        print(f"  {step.step.value:<22}{step.sessions:>5}{rate}")
    print(f"  by channel: {report.sessions_by_channel}")
    print(f"  checkouts by offering: {report.checkouts_by_offering}")
    print(f"  top queries: {report.top_queries}")
    print(f"  budgets mentioned: {report.budgets_mentioned}")
    print(f"  requested dates: {report.requested_dates}")


if __name__ == "__main__":
    main()
