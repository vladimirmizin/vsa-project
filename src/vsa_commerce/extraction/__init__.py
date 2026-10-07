"""LLM extraction for unstructured sources. Structured sources (e.g. a Shopify feed) map fields directly."""

from vsa_commerce.extraction.assemble import assemble_offering
from vsa_commerce.extraction.grounding import check_grounding
from vsa_commerce.extraction.llm import ChatModel, LLMOfferingExtractor, OfferingExtractor
from vsa_commerce.extraction.schema import ExtractedOffer, ExtractedOffering, ExtractionRequest

__all__ = [
    "ChatModel",
    "ExtractedOffer",
    "ExtractedOffering",
    "ExtractionRequest",
    "LLMOfferingExtractor",
    "OfferingExtractor",
    "assemble_offering",
    "check_grounding",
]
