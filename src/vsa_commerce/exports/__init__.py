"""Passive discovery channel: structured data for assistants and search engines that read, not call."""

from vsa_commerce.exports.feed import render_feed
from vsa_commerce.exports.jsonld import offering_jsonld, script_tag
from vsa_commerce.exports.llms_txt import render_llms_txt

__all__ = ["offering_jsonld", "render_feed", "render_llms_txt", "script_tag"]
