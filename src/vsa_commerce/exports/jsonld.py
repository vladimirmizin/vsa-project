"""schema.org JSON-LD for each offering, ready to paste into the business's own pages."""

from __future__ import annotations

import json
from typing import Any

from vsa_commerce.domain.models import (
    BillingInterval,
    Business,
    Catalog,
    DeliveryMode,
    EnrollmentMode,
    Offer,
    Offering,
    OfferingKind,
)

_SCHEMA_TYPE = {OfferingKind.COURSE: "Course", OfferingKind.SERVICE: "Service", OfferingKind.PRODUCT: "Product"}
_SOCIAL_HOSTS = ("instagram.com", "facebook.com", "youtube.com", "tiktok.com", "x.com", "twitter.com", "linkedin.com")
_ISO_INTERVAL = {
    BillingInterval.DAY: "D",
    BillingInterval.WEEK: "W",
    BillingInterval.MONTH: "M",
    BillingInterval.YEAR: "Y",
}


def organization(business: Business) -> dict[str, Any]:
    data: dict[str, Any] = {
        "@type": "Organization",
        "name": business.name,
        "alternateName": [n for n in business.brand_names if n != business.name],
        "url": str(business.website),
        "description": business.description,
    }
    if business.contact_email:
        data["email"] = business.contact_email
    profiles = [str(u) for u in business.links.values() if (u.host or "").removeprefix("www.").endswith(_SOCIAL_HOSTS)]
    if profiles:
        data["sameAs"] = profiles
    return data


def offering_jsonld(catalog: Catalog, offering: Offering) -> dict[str, Any]:
    provider = organization(catalog.business)
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": _SCHEMA_TYPE[offering.kind],
        "@id": f"{catalog.business.website}#{offering.id}",
        "name": offering.name,
        "description": offering.description or offering.summary,
        "offers": [_offer(o, provider) for o in offering.offers],
    }
    match offering.kind:
        case OfferingKind.COURSE:
            data["provider"] = provider
            if offering.audience.level:
                data["educationalLevel"] = offering.audience.level
            if offering.audience.prerequisites:
                data["coursePrerequisites"] = offering.audience.prerequisites
            if offering.curriculum:
                data["syllabusSections"] = [
                    {"@type": "Syllabus", "name": m.title, "description": "; ".join(m.points)}
                    for m in offering.curriculum
                ]
            data["hasCourseInstance"] = _course_instance(offering)
        case OfferingKind.SERVICE:
            data["provider"] = provider
        case OfferingKind.PRODUCT:
            data["brand"] = {"@type": "Brand", "name": catalog.business.name}
    return data


def _course_instance(offering: Offering) -> dict[str, Any]:
    instance: dict[str, Any] = {
        "@type": "CourseInstance",
        "courseMode": "online" if offering.delivery is DeliveryMode.ONLINE else offering.delivery.value,
        "instructor": [{"@type": "Person", "name": s.name, "description": s.bio} for s in offering.staff],
    }
    schedule = offering.schedule
    if schedule is not None:
        end_minutes = schedule.start_time.hour * 60 + schedule.start_time.minute + schedule.duration_minutes
        instance["courseSchedule"] = {
            "@type": "Schedule",
            "repeatFrequency": "P1W",
            "byDay": [f"https://schema.org/{d.name.capitalize()}" for d in schedule.weekdays],
            "startTime": f"{schedule.start_time:%H:%M}",
            "endTime": f"{end_minutes // 60 % 24:02d}:{end_minutes % 60:02d}",
            "duration": f"PT{schedule.duration_minutes}M",
            "scheduleTimezone": schedule.timezone,
        }
        if offering.enrollment.mode is EnrollmentMode.COHORT:
            instance["courseSchedule"]["startDate"] = min(offering.enrollment.cohort_start_dates).isoformat()
    sessions = next((o.sessions_included for o in offering.offers if o.sessions_included), None)
    if sessions:
        instance["courseWorkload"] = f"{sessions} live sessions"
    return instance


def _offer(offer: Offer, seller: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "@type": "Offer",
        "name": offer.name,
        "price": f"{offer.price.amount:.2f}",
        "priceCurrency": offer.price.currency,
        "seller": {"@type": "Organization", "name": seller["name"]},
    }
    if offer.checkout.url:
        data["url"] = str(offer.checkout.url)
    if offer.available is not None:
        data["availability"] = "https://schema.org/" + ("InStock" if offer.available else "OutOfStock")
    if offer.recurring:
        data["priceSpecification"] = {
            "@type": "UnitPriceSpecification",
            "price": f"{offer.price.amount:.2f}",
            "priceCurrency": offer.price.currency,
            "billingDuration": f"P{offer.recurring.interval_count}{_ISO_INTERVAL[offer.recurring.interval]}",
        }
    if offer.list_price:
        data.setdefault("priceSpecification", {"@type": "UnitPriceSpecification"})
        data["priceSpecification"]["referencePrice"] = {
            "@type": "UnitPriceSpecification",
            "priceType": "https://schema.org/ListPrice",
            "price": f"{offer.list_price.amount:.2f}",
            "priceCurrency": offer.list_price.currency,
        }
    if offer.refundable is False:
        data["hasMerchantReturnPolicy"] = {
            "@type": "MerchantReturnPolicy",
            "returnPolicyCategory": "https://schema.org/MerchantReturnNotPermitted",
        }
    return data


def script_tag(data: dict[str, Any]) -> str:
    """The snippet a site owner pastes into the page head (Tilda: Page settings > HEAD)."""
    body = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{body}\n</script>\n'
