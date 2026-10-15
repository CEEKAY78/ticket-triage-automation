import json

import pytest

from fakes import ScriptedLLM, label
from triage.classify import LLMUnavailableError, classify, route

TICKET = ("My wardrobe from order TY-2048813 arrived with a broken door. "
          "Contact me at jan.nowak@example.com or +48 601 234 567.")


def test_ticket_is_classified_and_order_number_extracted():
    t = classify(TICKET, ScriptedLLM(label("damaged_item", "high")))
    assert (t.category, t.urgency, t.language) == ("damaged_item", "high", "en")
    assert t.order_ids == ["TY-2048813"]
    assert t.queue == "auto" and t.attempts == 1


def test_the_model_never_sees_personal_data():
    llm = ScriptedLLM(label())
    classify(TICKET, llm)
    prompt = json.dumps(llm.prompts[0])
    assert "jan.nowak" not in prompt and "601 234" not in prompt
    assert "[EMAIL]" in prompt and "TY-2048813" in prompt


def test_invalid_reply_is_retried_once_then_sent_to_review():
    bad = json.dumps({"category": "furniture_rage", "urgency": "normal", "language": "en",
                      "confidence": 0.9, "summary": "?"})
    t = classify(TICKET, ScriptedLLM("not json", label()))
    assert t.queue == "auto" and t.attempts == 2
    t = classify(TICKET, ScriptedLLM(bad, "{}"))
    assert t.queue == "review" and t.category == "other" and t.attempts == 2
    assert "invalid" in t.review_reason


def test_low_confidence_goes_to_human_review():
    t = classify(TICKET, ScriptedLLM(label(confidence=0.55)))
    assert t.queue == "review" and "confidence" in t.review_reason


def test_model_outage_raises_so_the_caller_can_dead_letter():
    with pytest.raises(LLMUnavailableError):
        classify(TICKET, ScriptedLLM(ConnectionError("ollama down")))


@pytest.mark.parametrize(
    ("category", "urgency", "team", "sla_hours"),
    [
        ("damaged_item", "high", "claims", 4),
        ("delivery_delay", "normal", "logistics", 24),
        ("order_change", "high", "logistics", 4),
        ("return_refund", "low", "finance", 72),
        ("payment_invoice", "normal", "finance", 24),
        ("assembly_help", "normal", "support", 24),
        ("product_question", "low", "support", 72),
        ("other", "normal", "support", 24),
    ],
)
def test_routing_by_category_and_sla_by_urgency(category, urgency, team, sla_hours):
    t = classify(TICKET, ScriptedLLM(label(category, urgency)))
    assert route(t) == (team, sla_hours)
