"""
Ticket classifier.

Sends the ticket to the *fast* model tier and asks for a strict JSON object
describing category, priority, sentiment and a confidence score. Using the
cheap model here is intentional: classification is high-volume and well within
a small model's ability, which is the first cost-optimization lever.

The prompt forces JSON-only output; parsing is defensive (strips code fences,
falls back to a safe default if the model returns something unexpected) so a
malformed response degrades gracefully instead of crashing the pipeline.
"""
from __future__ import annotations

import json
import re

from .llm_client import llm
from .schemas import Category, Classification, Priority, Sentiment, Ticket

_SYSTEM = """You are a support-ticket triage classifier. Read the ticket and \
return ONLY a JSON object (no prose, no markdown) with exactly these keys:

  "category":   one of ["billing","technical","account","product_question",
                "refund","bug_report","feature_request","security","other"]
  "priority":   one of ["urgent","high","medium","low"]
  "sentiment":  one of ["angry","frustrated","neutral","positive"]
  "confidence": a float between 0 and 1 (your confidence in the category)
  "reasoning":  one short sentence explaining the category choice

Priority guidance: anything indicating an outage, lost access, security issue, \
or explicit urgency is "urgent" or "high". Pure questions / feature ideas are \
usually "low". Return valid JSON only."""

_FENCE_RE = re.compile(r"```(?:json)?|```", re.IGNORECASE)


def _coerce_enum(value: str, enum_cls, default):
    try:
        return enum_cls(value)
    except Exception:
        return default


def classify(ticket: Ticket) -> Classification:
    user = f"SUBJECT: {ticket.subject}\n\nBODY:\n{ticket.body}"
    raw = llm.complete(_SYSTEM, user, tier="fast", max_tokens=300, temperature=0.0)
    cleaned = _FENCE_RE.sub("", raw).strip()

    # Extract the first {...} block in case the model added stray text.
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]

    try:
        data = json.loads(cleaned)
    except Exception:
        data = {}

    try:
        confidence = float(data.get("confidence", 0.5))
    except Exception:
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    return Classification(
        category=_coerce_enum(data.get("category", "other"), Category, Category.OTHER),
        priority=_coerce_enum(data.get("priority", "medium"), Priority, Priority.MEDIUM),
        sentiment=_coerce_enum(data.get("sentiment", "neutral"), Sentiment, Sentiment.NEUTRAL),
        confidence=confidence,
        reasoning=str(data.get("reasoning", ""))[:200],
    )
