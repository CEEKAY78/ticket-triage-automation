"""Mask personal data before a ticket leaves the service (to the LLM, logs or the database).

Masked: e-mail addresses, Polish phone numbers (9 digits, optional +48) and IBAN account
numbers. Kept: order numbers ("TY-1234567" or "#1234567", normalised to "TY-1234567"), because
routing needs them and they identify an order, not a person.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?\d{4}){4,7}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w#-])(?:\+48[ -]?)?\d{3}[ -]?\d{3}[ -]?\d{3}(?!\d)")
_ORDER = re.compile(r"(?:\bTY-|#)(\d{7})\b")

_RULES = [("iban", _IBAN, "[IBAN]"), ("email", _EMAIL, "[EMAIL]"), ("phone", _PHONE, "[PHONE]")]


@dataclass
class Redacted:
    text: str
    counts: dict[str, int] = field(default_factory=dict)
    order_ids: list[str] = field(default_factory=list)


def redact(text: str) -> Redacted:
    counts: Counter[str] = Counter()
    out = text
    for name, pattern, mask in _RULES:
        out, n = pattern.subn(mask, out)
        if n:
            counts[name] += n
    order_ids = list(dict.fromkeys(f"TY-{m}" for m in _ORDER.findall(out)))
    return Redacted(text=out, counts=dict(counts), order_ids=order_ids)
