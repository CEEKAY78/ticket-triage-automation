"""Fake at the external boundary only: the chat model."""

import json


class ScriptedLLM:
    """Returns scripted replies in order (an Exception instance is raised) and records prompts."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def chat(self, messages, schema=None):
        self.prompts.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def label(category="damaged_item", urgency="normal", language="en", confidence=0.95,
          summary="Item arrived damaged."):
    return json.dumps({"category": category, "urgency": urgency, "language": language,
                       "confidence": confidence, "summary": summary})
