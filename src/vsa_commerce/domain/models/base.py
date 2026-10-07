from __future__ import annotations

from enum import IntEnum
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class Model(BaseModel):
    # extra="forbid": a typo in catalog data or an invented field from the LLM must fail loudly
    model_config = ConfigDict(frozen=True, extra="forbid")


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA timezone: {value!r}") from exc
    return value


# IANA name only: abbreviations like "PDT" are correct for half of the year
Timezone = Annotated[str, AfterValidator(_validate_timezone)]
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)]
NonEmptyStr = Annotated[str, Field(min_length=1)]


class Weekday(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6
