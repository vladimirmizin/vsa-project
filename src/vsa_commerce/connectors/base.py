"""Connector contract: ``fetch`` does I/O only, ``extract`` turns documents into catalog data."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from vsa_commerce.connectors.http import SourceDocument


class PageSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: HttpUrl
    offering_id: str


class SourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    business_id: str
    platform: str
    pages: list[PageSpec] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class SourceConnector(ABC):
    platform: ClassVar[str]

    def __init__(self, config: SourceConfig, http: httpx.Client | None = None) -> None:
        if config.platform != self.platform:
            raise ValueError(f"{type(self).__name__} cannot handle platform {config.platform!r}")
        self.config = config
        self.http = http

    @abstractmethod
    def fetch(self) -> list[SourceDocument]:
        """Raise SourceUnavailableError if the source cannot be read."""

    @abstractmethod
    def extract(self, documents: list[SourceDocument]) -> list[dict[str, Any]]:
        """Unvalidated offering dicts; the caller applies owner rules and validates."""
