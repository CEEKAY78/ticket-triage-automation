"""Classify a customer ticket with an LLM and route it to a team with an SLA.

Steps: mask personal data -> ask the model for a JSON label (structured output) -> validate it
against the allowed values -> one retry with the validation error -> otherwise a human-review
fallback. Low-confidence labels also go to human review. If the model cannot be reached at
all, ``LLMUnavailableError`` is raised so the caller can park the ticket in a dead-letter queue
and retry later instead of losing it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from triage.privacy import redact

CATEGORIES = {
    "delivery_delay": "the order is late, not shipped or tracking does not move",
    "damaged_item": "item arrived broken, scratched, wrong or with missing parts",
    "assembly_help": "how to assemble or install the furniture",
    "return_refund": "return an item, withdraw from the purchase or get money back",
    "order_change": "change address, delivery date, colour or cancel before shipping",
    "payment_invoice": "payment problems, invoice requests or VAT data",
    "product_question": "questions before buying: sizes, materials, availability",
    "other": "anything else",
}
URGENCIES = {"high", "normal", "low"}
LANGUAGES = {"pl", "en"}
TEAM = {
    "delivery_delay": "logistics",
    "order_change": "logistics",
    "damaged_item": "claims",
    "return_refund": "finance",
    "payment_invoice": "finance",
    "assembly_help": "support",
    "product_question": "support",
    "other": "support",
}
SLA_HOURS = {"high": 4, "normal": 24, "low": 72}
MIN_CONFIDENCE = 0.7

LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": sorted(CATEGORIES)},
        "urgency": {"type": "string", "enum": sorted(URGENCIES)},
        "language": {"type": "string", "enum": sorted(LANGUAGES)},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
    },
    "required": ["category", "urgency", "language", "confidence", "summary"],
}

SYSTEM = (
    "You triage customer e-mails for an online furniture shop. Return JSON only with: "
    "category, urgency, language (pl or en), confidence (0-1, how sure you are of the "
    "category) and a one-sentence English summary.\n\nCategories:\n"
    + "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
    + "\n\nUrgency: high = damaged item, safety issue, angry customer, or the delivery is "
    "today/overdue by more than a week; low = general question with no deadline; otherwise "
    "normal. Personal data is masked as [EMAIL], [PHONE], [IBAN]."
)


class ChatClient(Protocol):
    def chat(self, messages: list[dict], schema: dict | None = None) -> str: ...


class LLMUnavailableError(Exception):
    """The model could not be reached (network, server down, timeout)."""


@dataclass
class Triage:
    category: str = "other"
    urgency: str = "normal"
    language: str = "en"
    confidence: float = 0.0
    summary: str = ""
    order_ids: list[str] = field(default_factory=list)
    pii_masked: dict[str, int] = field(default_factory=dict)
    queue: str = "review"  # auto | review
    review_reason: str = ""
    attempts: int = 0


def _validate(reply: str) -> tuple[dict | None, str]:
    try:
        data = json.loads(reply)
    except json.JSONDecodeError:
        return None, "invalid JSON"
    if not isinstance(data, dict):
        return None, "invalid: not a JSON object"
    problems = []
    if data.get("category") not in CATEGORIES:
        problems.append(f"category must be one of {sorted(CATEGORIES)}")
    if data.get("urgency") not in URGENCIES:
        problems.append("urgency must be high, normal or low")
    if data.get("language") not in LANGUAGES:
        problems.append("language must be pl or en")
    conf = data.get("confidence")
    if not isinstance(conf, int | float) or not 0 <= conf <= 1:
        problems.append("confidence must be a number between 0 and 1")
    if problems:
        return None, "invalid: " + "; ".join(problems)
    return data, ""


def classify(text: str, llm: ChatClient) -> Triage:
    masked = redact(text)
    result = Triage(order_ids=masked.order_ids, pii_masked=masked.counts)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": masked.text}]
    for attempt in (1, 2):
        result.attempts = attempt
        try:
            reply = llm.chat(messages, schema=LABEL_SCHEMA)
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise LLMUnavailableError(str(exc)) from exc
        data, problem = _validate(reply)
        if data is None:
            result.review_reason = problem
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"Your reply was {problem}. Reply again "
                                                     "with valid JSON only."}]
            continue
        result.category = data["category"]
        result.urgency = data["urgency"]
        result.language = data["language"]
        result.confidence = float(data["confidence"])
        result.summary = str(data.get("summary", ""))
        if result.confidence < MIN_CONFIDENCE:
            result.queue = "review"
            result.review_reason = f"low confidence {result.confidence:.2f}"
        else:
            result.queue = "auto"
            result.review_reason = ""
        return result
    return result  # still invalid after the retry: category "other", human review


def route(t: Triage) -> tuple[str, int]:
    """(team, SLA in hours)."""
    return TEAM[t.category], SLA_HOURS[t.urgency]
