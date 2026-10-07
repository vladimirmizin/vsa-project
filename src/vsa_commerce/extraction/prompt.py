from __future__ import annotations

import json

from vsa_commerce.extraction.schema import ExtractedOffering, ExtractionRequest

SYSTEM_PROMPT = """\
You convert a business's web page into structured catalog data.

Rules:
- Use only facts stated on the page. Never invent prices, dates, people, platforms or links.
  If something is not stated, leave the field empty or null.
- Report what the page says literally. Business rules that override the page are applied later,
  so if the page advertises a start date, describe enrollment as a cohort starting on that date
  (the next occurrence of that date on or after {fetched_on}).
- Prices are numbers with a 3-letter currency code. '$' means USD unless the page says otherwise.
  A crossed-out higher price is list_price. A per-class figure that is just the package price
  divided by the number of classes is NOT a separate offer; keep it in `advertised`.
- Schedules: store one anchor timezone as an IANA name (e.g. America/Los_Angeles for PDT/PST)
  with the local start time in that zone. Put every other timezone the page lists into
  display_timezones as IANA names. Weekdays are numbers, Monday=0 ... Sunday=6.
- level_rank is the number in a label such as 'Level 3'.
- checkout_url must be exactly one of the payment links provided, or null.
- related offerings may only use these ids: {other_ids}.
- Record contradictions on the page in `conflicts`.

Return a single JSON object that matches this JSON Schema:
{schema}
"""

USER_PROMPT = """\
URL: {url}
Title: {title}

Payment links on the page:
{links}

Page text:
{text}
"""


def build_messages(request: ExtractionRequest) -> list[dict[str, str]]:
    system = SYSTEM_PROMPT.format(
        fetched_on=request.fetched_on.isoformat(),
        other_ids=", ".join(request.other_offering_ids) or "(none)",
        schema=json.dumps(ExtractedOffering.model_json_schema()),
    )
    user = USER_PROMPT.format(
        url=request.source_url,
        title=request.page_title,
        links="\n".join(f"- {link}" for link in request.payment_links) or "(none)",
        text=request.page_text,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def feedback_message(problems: list[str]) -> dict[str, str]:
    return {
        "role": "user",
        "content": "Fix these problems and return the full JSON again:\n- " + "\n- ".join(problems),
    }
