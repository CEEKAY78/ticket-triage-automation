"""Thin client for a local Ollama server (structured JSON output)."""

from __future__ import annotations

import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


class OllamaChat:
    def __init__(self, model: str, timeout_s: float = 120.0):
        self.model = model
        self.timeout_s = timeout_s

    def chat(self, messages: list[dict], schema: dict | None = None) -> str:
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": {"temperature": 0.0, "num_ctx": 4096}}
        if schema is not None:
            body["format"] = schema
        try:
            resp = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=self.timeout_s)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ConnectionError(f"Ollama request failed: {exc}") from exc
        return resp.json()["message"]["content"]
