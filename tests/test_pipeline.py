from fakes import ScriptedLLM, label

from triage.pipeline import Pipeline

TICKET = {"ticket_id": "T-1", "channel": "email",
          "text": "Order TY-2048813 arrived broken. jan@example.com"}


def test_processed_ticket_is_stored_without_personal_data(tmp_path):
    p = Pipeline(tmp_path / "t.sqlite3", ScriptedLLM(label("damaged_item", "high")))
    out = p.process(TICKET)
    assert out["status"] == "routed" and out["team"] == "claims" and out["sla_hours"] == 4
    stored = p.get("T-1")
    assert stored["category"] == "damaged_item" and stored["order_ids"] == ["TY-2048813"]
    assert "jan@example.com" not in str(stored) and "[EMAIL]" in stored["masked_text"]


def test_same_ticket_twice_is_processed_once(tmp_path):
    llm = ScriptedLLM(label())
    p = Pipeline(tmp_path / "t.sqlite3", llm)
    first = p.process(TICKET)
    second = p.process(TICKET)
    assert second == {**first, "duplicate": True}
    assert len(llm.prompts) == 1


def test_low_confidence_ticket_lands_in_the_review_queue(tmp_path):
    p = Pipeline(tmp_path / "t.sqlite3", ScriptedLLM(label(confidence=0.4)))
    assert p.process(TICKET)["status"] == "review"
    assert [t["ticket_id"] for t in p.review_queue()] == ["T-1"]


def test_model_outage_parks_the_ticket_and_a_retry_completes_it(tmp_path):
    llm = ScriptedLLM(ConnectionError("down"), label("delivery_delay"))
    p = Pipeline(tmp_path / "t.sqlite3", llm)
    assert p.process(TICKET)["status"] == "dead_letter"
    assert [t["ticket_id"] for t in p.dead_letters()] == ["T-1"]
    assert p.retry_dead_letters() == {"retried": 1, "routed": 1, "still_failing": 0}
    assert p.dead_letters() == [] and p.get("T-1")["team"] == "logistics"


def test_metrics_count_automation_rate_and_time_saved(tmp_path):
    llm = ScriptedLLM(label(), label(confidence=0.3), label())
    p = Pipeline(tmp_path / "t.sqlite3", llm, manual_minutes_per_ticket=3.0)
    for i in range(3):
        p.process({**TICKET, "ticket_id": f"T-{i}"})
    m = p.metrics()
    assert m["tickets"] == 3 and m["auto_routed"] == 2 and m["review"] == 1
    assert m["automation_rate"] == round(2 / 3, 3)
    assert m["minutes_saved"] == 6.0
