from __future__ import annotations


class VsaCommerceError(Exception):
    pass


class CatalogNotFoundError(VsaCommerceError, LookupError):
    pass


class OwnerRuleError(VsaCommerceError, ValueError):
    pass


class SourceUnavailableError(VsaCommerceError, RuntimeError):
    """The source could not be read; callers keep the last good snapshot."""


class ExtractionError(VsaCommerceError, ValueError):
    """The source was read but could not be turned into valid catalog data."""


class ToolInputError(VsaCommerceError, ValueError):
    """Bad input from the assistant. The message is written for the model to correct itself."""
