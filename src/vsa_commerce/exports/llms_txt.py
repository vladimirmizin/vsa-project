"""``llms.txt``: a short Markdown brief of the business for language models (llmstxt.org)."""

from __future__ import annotations

from vsa_commerce.domain.models import Catalog, EnrollmentMode, Offering


def render_llms_txt(catalog: Catalog, *, mcp_url: str | None = None, feed_url: str | None = None) -> str:
    business = catalog.business
    lines = [
        f"# {business.name}",
        "",
        f"> {business.description} Also known as: {', '.join(business.brand_names)}.",
        "",
    ]
    if mcp_url or feed_url:
        lines += ["## For AI assistants", ""]
        if mcp_url:
            lines.append(f"- MCP server with search, details, availability and checkout tools: {mcp_url}")
        if feed_url:
            lines.append(f"- Machine-readable catalog: {feed_url}")
        lines.append("")
    lines += ["## Offerings", ""]
    for offering in catalog.offerings:
        lines += _offering(offering)
    lines += ["## Contact", "", f"- Website: {business.website}"]
    if business.contact_email:
        lines.append(f"- Email: {business.contact_email}")
    return "\n".join(lines) + "\n"


def _offering(offering: Offering) -> list[str]:
    lines = [f"### {offering.name}", "", offering.summary, ""]
    if offering.audience.level:
        lines.append(f"- Level: {offering.audience.level}")
    for offer in offering.offers:
        terms = offer.billing_text()
        if offer.refundable is False:
            terms += ", non-refundable"
        lines.append(f"- Price: {terms}")
        if offer.checkout.url:
            lines.append(f"- Enroll / buy: {offer.checkout.url}")
    if offering.schedule:
        s = offering.schedule
        days = " and ".join(d.name.capitalize() for d in s.weekdays)
        lines.append(
            f"- Schedule: every {days} at {s.start_time:%H:%M} {s.timezone} time, {s.duration_minutes} minutes"
            " (local times in any timezone are available through the MCP tools)"
        )
    if offering.enrollment.mode is EnrollmentMode.ROLLING:
        lines.append("- Enrollment: open continuously; join any time and start at the next session")
    if offering.staff:
        lines.append(f"- Led by: {', '.join(s.name for s in offering.staff)}")
    lines.append(f"- Source: {offering.provenance.source_url}")
    return [*lines, ""]
