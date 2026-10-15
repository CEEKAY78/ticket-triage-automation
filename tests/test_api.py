from fastapi.testclient import TestClient

from fakes import ScriptedLLM, label
from triage.api import create_app

TOKEN = "test-token"
TICKET = {"ticket_id": "T-9", "channel": "form", "text": "Where is my order TY-1234567?"}


def client(tmp_path, *replies):
    return TestClient(create_app(tmp_path / "a.sqlite3", ScriptedLLM(*replies), token=TOKEN))


def test_webhook_requires_the_shared_token(tmp_path):
    c = client(tmp_path, label())
    assert c.post("/tickets", json=TICKET).status_code == 401
    assert c.post("/tickets", json=TICKET, headers={"X-Webhook-Token": "nope"}).status_code == 401


def test_webhook_routes_a_ticket(tmp_path):
    c = client(tmp_path, label("delivery_delay"))
    r = c.post("/tickets", json=TICKET, headers={"X-Webhook-Token": TOKEN})
    assert r.status_code == 200
    assert r.json()["team"] == "logistics" and r.json()["status"] == "routed"


def test_invalid_payload_is_rejected(tmp_path):
    c = client(tmp_path, label())
    r = c.post("/tickets", json={"ticket_id": "", "text": ""}, headers={"X-Webhook-Token": TOKEN})
    assert r.status_code == 422


def test_queues_and_metrics_are_exposed(tmp_path):
    c = client(tmp_path, label(confidence=0.2))
    h = {"X-Webhook-Token": TOKEN}
    c.post("/tickets", json=TICKET, headers=h)
    assert [t["ticket_id"] for t in c.get("/review-queue", headers=h).json()] == ["T-9"]
    assert c.get("/metrics", headers=h).json()["review"] == 1
    assert c.get("/health").json() == {"status": "ok"}
