"""LLM extraction: validate, check grounding, send problems back once, otherwise fail."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Protocol

from pydantic import ValidationError

from vsa_commerce.domain.models import Offering
from vsa_commerce.errors import ExtractionError
from vsa_commerce.extraction.assemble import assemble_offering
from vsa_commerce.extraction.grounding import check_grounding
from vsa_commerce.extraction.prompt import build_messages, feedback_message
from vsa_commerce.extraction.schema import ExtractedOffering, ExtractionRequest


class OfferingExtractor(Protocol):
    def extract(self, request: ExtractionRequest) -> ExtractedOffering: ...


class ChatModel(Protocol):
    def complete_json(self, messages: list[dict[str, str]]) -> str: ...


class LLMOfferingExtractor:
    def __init__(self, chat: ChatModel, *, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.chat = chat
        self.max_attempts = max_attempts

    def extract(self, request: ExtractionRequest) -> ExtractedOffering:
        messages = build_messages(request)
        problems: list[str] = []
        for _ in range(self.max_attempts):
            raw = self.chat.complete_json(messages)
            extracted, problems = _evaluate(raw, request)
            if extracted is not None:
                return extracted
            messages += [{"role": "assistant", "content": raw}, feedback_message(problems)]
        raise ExtractionError(f"{request.source_url}: extraction rejected: {'; '.join(problems)}")


def _evaluate(raw: str, request: ExtractionRequest) -> tuple[ExtractedOffering | None, list[str]]:
    try:
        extracted = ExtractedOffering.model_validate(json.loads(raw))
    except json.JSONDecodeError as exc:
        return None, [f"output is not valid JSON: {exc}"]
    except ValidationError as exc:
        return None, [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
    problems = check_grounding(extracted, request)
    if problems:
        return None, problems
    # the assembled record must also be a valid catalog offering (e.g. a checkout needs a usable url)
    try:
        Offering.model_validate(assemble_offering(extracted, request, platform="check", fetched_at=datetime.now(UTC)))
    except ValidationError as exc:
        return None, [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
    return extracted, []
