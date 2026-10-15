"""Ticket pipeline: idempotent processing, SQLite store, review and dead-letter queues, metrics.

Only the masked text is ever stored. A ticket the model could not classify because it was
unreachable is parked as ``dead_letter`` and re-processed by ``retry_dead_letters`` (n8n calls
it on a schedule), so an outage delays tickets but never loses them.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from triage.classify import ChatClient, LLMUnavailableError, classify, route
from triage.privacy import redact

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    channel TEXT,
    masked_text TEXT NOT NULL,
    status TEXT NOT NULL,            -- routed | review | dead_letter
    category TEXT, urgency TEXT, language TEXT, confidence REAL, summary TEXT,
    order_ids TEXT, pii_masked TEXT,
    team TEXT, sla_hours INTEGER, review_reason TEXT, attempts INTEGER, error TEXT,
    updated_at TEXT NOT NULL
)
"""

_RESULT_KEYS = ["ticket_id", "status", "category", "urgency", "team", "sla_hours",
                "order_ids", "review_reason"]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Pipeline:
    def __init__(self, db_path: Path | str, llm: ChatClient,
                 manual_minutes_per_ticket: float = 3.0):
        self.db_path = Path(db_path)
        self.llm = llm
        self.manual_minutes = manual_minutes_per_ticket
        with self._db() as con:
            con.execute(_SCHEMA)

    def _db(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _row(self, ticket_id: str) -> dict | None:
        with self._db() as con:
            row = con.execute("SELECT * FROM tickets WHERE ticket_id = ?", [ticket_id]).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["order_ids"] = json.loads(d["order_ids"] or "[]")
        d["pii_masked"] = json.loads(d["pii_masked"] or "{}")
        return d

    def get(self, ticket_id: str) -> dict | None:
        return self._row(ticket_id)

    def _result(self, ticket_id: str) -> dict:
        row = self._row(ticket_id)
        assert row is not None
        return {k: row[k] for k in _RESULT_KEYS}

    def _classify_and_save(self, ticket_id: str, channel: str, masked_text: str) -> None:
        try:
            t = classify(masked_text, self.llm)
        except LLMUnavailableError as exc:
            values = dict(status="dead_letter", error=str(exc), attempts=None, category=None,
                          urgency=None, language=None, confidence=None, summary=None,
                          order_ids=json.dumps(redact(masked_text).order_ids), pii_masked=None,
                          team=None, sla_hours=None, review_reason="model unavailable")
        else:
            team, sla = route(t)
            values = dict(status="routed" if t.queue == "auto" else "review", error=None,
                          attempts=t.attempts, category=t.category, urgency=t.urgency,
                          language=t.language, confidence=t.confidence, summary=t.summary,
                          order_ids=json.dumps(t.order_ids), pii_masked=json.dumps(t.pii_masked),
                          team=team, sla_hours=sla, review_reason=t.review_reason)
        cols = ["ticket_id", "channel", "masked_text", *values, "updated_at"]
        params = [ticket_id, channel, masked_text, *values.values(), _now()]
        with self._db() as con:
            con.execute(
                f"INSERT OR REPLACE INTO tickets ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})",
                params,
            )

    def process(self, ticket: dict) -> dict:
        ticket_id = str(ticket["ticket_id"])
        existing = self._row(ticket_id)
        if existing is not None and existing["status"] != "dead_letter":
            return {**self._result(ticket_id), "duplicate": True}
        masked = redact(str(ticket["text"])).text
        self._classify_and_save(ticket_id, str(ticket.get("channel", "")), masked)
        return self._result(ticket_id)

    def _by_status(self, status: str) -> list[dict]:
        with self._db() as con:
            ids = [r[0] for r in con.execute(
                "SELECT ticket_id FROM tickets WHERE status = ? ORDER BY updated_at, ticket_id",
                [status])]
        return [self._result(i) for i in ids]

    def review_queue(self) -> list[dict]:
        return self._by_status("review")

    def dead_letters(self) -> list[dict]:
        return self._by_status("dead_letter")

    def retry_dead_letters(self) -> dict[str, int]:
        parked = self.dead_letters()
        for item in parked:
            row = self._row(item["ticket_id"])
            assert row is not None
            self._classify_and_save(row["ticket_id"], row["channel"], row["masked_text"])
        still = {t["ticket_id"] for t in self.dead_letters()}
        routed = sum(1 for t in parked if t["ticket_id"] not in still
                     and self._row(t["ticket_id"])["status"] == "routed")
        return {"retried": len(parked), "routed": routed, "still_failing": len(still)}

    def metrics(self) -> dict:
        with self._db() as con:
            counts = dict(con.execute("SELECT status, count(*) FROM tickets GROUP BY 1").fetchall())
        auto = counts.get("routed", 0)
        total = sum(counts.values())
        return {
            "tickets": total,
            "auto_routed": auto,
            "review": counts.get("review", 0),
            "dead_letter": counts.get("dead_letter", 0),
            "automation_rate": round(auto / total, 3) if total else 0.0,
            "minutes_saved": round(auto * self.manual_minutes, 1),
            "manual_minutes_per_ticket": self.manual_minutes,
        }
