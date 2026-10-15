import json
from collections import Counter
from pathlib import Path

import pytest

from triage.classify import CATEGORIES
from triage.privacy import redact

DATA = Path(__file__).resolve().parents[1] / "data" / "tickets_labelled.jsonl"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="run scripts/make_dataset.py")


def rows():
    return [json.loads(x) for x in DATA.read_text(encoding="utf-8").splitlines() if x]


def test_balanced_over_categories_and_languages():
    r = rows()
    assert len(r) == 96
    assert Counter(x["category"] for x in r) == {c: 12 for c in CATEGORIES}
    assert Counter(x["language"] for x in r) == {"pl": 48, "en": 48}


def test_masking_removes_every_planted_e_mail_phone_and_iban():
    for x in rows():
        masked = redact(x["text"]).text
        assert "@example.com" not in masked and "+48" not in masked
        assert not any(tok.startswith("PL") and tok[2:].isdigit() for tok in masked.split())
