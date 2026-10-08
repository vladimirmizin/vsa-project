from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class EventType(StrEnum):
    SEARCH = "search"
    OFFERING_VIEWED = "offering_viewed"
    AVAILABILITY_CHECKED = "availability_checked"
    CHECKOUT_CREATED = "checkout_created"
    PAYMENT_COMPLETED = "payment_completed"


FUNNEL = (
    EventType.SEARCH,
    EventType.OFFERING_VIEWED,
    EventType.AVAILABILITY_CHECKED,
    EventType.CHECKOUT_CREATED,
    EventType.PAYMENT_COMPLETED,
)


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    business_id: str
    session_id: str
    channel: str = Field(description="Which assistant integration produced the event: 'mcp', 'deepseek', ...")
    type: EventType
    offering_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
