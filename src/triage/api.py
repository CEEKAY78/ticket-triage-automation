"""HTTP API called by the n8n workflow (webhook in, routing decision out).

    uvicorn triage.api:app --port 8000

Every call except /health needs the shared secret in the ``X-Webhook-Token`` header (set
``TRIAGE_TOKEN`` in the environment; the n8n workflow sends the same value).
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from triage.classify import ChatClient
from triage.pipeline import Pipeline


class TicketIn(BaseModel):
    ticket_id: str = Field(min_length=1, max_length=64)
    channel: str = Field(default="email", max_length=32)
    text: str = Field(min_length=1, max_length=10_000)


def create_app(db_path: Path | str, llm: ChatClient, token: str) -> FastAPI:
    pipeline = Pipeline(db_path, llm)
    app = FastAPI(title="Ticket triage")

    def check_token(x_webhook_token: str | None = Header(default=None)) -> None:
        if not x_webhook_token or not secrets.compare_digest(x_webhook_token, token):
            raise HTTPException(status_code=401, detail="missing or wrong X-Webhook-Token")

    auth = [Depends(check_token)]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/tickets", dependencies=auth)
    def post_ticket(ticket: TicketIn) -> dict:
        return pipeline.process(ticket.model_dump())

    @app.get("/review-queue", dependencies=auth)
    def review_queue() -> list[dict]:
        return pipeline.review_queue()

    @app.get("/dead-letters", dependencies=auth)
    def dead_letters() -> list[dict]:
        return pipeline.dead_letters()

    @app.post("/dead-letters/retry", dependencies=auth)
    def retry() -> dict:
        return pipeline.retry_dead_letters()

    @app.get("/metrics", dependencies=auth)
    def metrics() -> dict:
        return pipeline.metrics()

    return app


def _default_app() -> FastAPI:
    from triage.ollama import OllamaChat

    root = Path(__file__).resolve().parents[2]
    (root / "data").mkdir(exist_ok=True)
    return create_app(root / "data" / "tickets.sqlite3",
                      OllamaChat(os.environ.get("TRIAGE_MODEL", "qwen2.5:7b-instruct")),
                      token=os.environ.get("TRIAGE_TOKEN", "change-me"))


def __getattr__(name: str):  # lazy, so tests importing create_app never touch Ollama
    if name == "app":
        return _default_app()
    raise AttributeError(name)
