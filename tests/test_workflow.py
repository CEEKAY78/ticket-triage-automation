"""Static checks of the exported n8n workflow (it is code too)."""

import json
from pathlib import Path

WF = json.loads((Path(__file__).resolve().parents[1] / "n8n" / "ticket-triage.workflow.json")
                .read_text(encoding="utf-8"))
NODES = {n["name"]: n for n in WF["nodes"]}


def test_every_connection_points_to_an_existing_node():
    for source, outputs in WF["connections"].items():
        assert source in NODES
        for branch in outputs["main"]:
            for target in branch:
                assert target["node"] in NODES


def test_api_call_is_retried_and_has_an_error_branch():
    call = NODES["Classify and route (triage API)"]
    assert call["retryOnFail"] and call["maxTries"] == 3
    assert call["onError"] == "continueErrorOutput"
    assert len(WF["connections"][call["name"]]["main"]) == 2


def test_secret_comes_from_the_environment_not_the_file():
    text = json.dumps(WF)
    assert "$env.TRIAGE_TOKEN" in text
    assert "change-me" not in text and "test-token" not in text


def test_every_webhook_outcome_gets_a_reply():
    replies = {n for n, v in NODES.items() if v["type"].endswith("respondToWebhook")}
    switch_targets = {t["node"] for b in WF["connections"]["By status"]["main"] for t in b}
    assert switch_targets | {"Reply: service down"} == replies
