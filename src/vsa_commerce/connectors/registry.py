"""Platform name -> connector. Adding a platform is one class and one line here."""

from __future__ import annotations

import httpx

from vsa_commerce.connectors.base import SourceConfig, SourceConnector
from vsa_commerce.connectors.shopify import ShopifyConnector
from vsa_commerce.connectors.tilda import TildaConnector
from vsa_commerce.extraction import OfferingExtractor

STRUCTURED: dict[str, type[SourceConnector]] = {"shopify": ShopifyConnector}
NEEDS_EXTRACTOR = {"tilda"}
PLATFORMS = sorted({*STRUCTURED, *NEEDS_EXTRACTOR})


def build_connector(
    config: SourceConfig, *, extractor: OfferingExtractor | None = None, http: httpx.Client | None = None
) -> SourceConnector:
    if config.platform in STRUCTURED:
        return STRUCTURED[config.platform](config, http)
    if config.platform == TildaConnector.platform:
        if extractor is None:
            raise ValueError("tilda pages need an LLM extractor")
        return TildaConnector(config, extractor, http)
    raise ValueError(f"no connector for platform {config.platform!r}; known: {', '.join(PLATFORMS)}")


def needs_extractor(platform: str) -> bool:
    return platform in NEEDS_EXTRACTOR
