"""
Unified LLM client.

One `complete()` interface, three real backends (Anthropic, OpenAI, Gemini)
reached over plain HTTP with `httpx`, plus a deterministic MOCK backend used
when no API key is configured.

Why raw HTTP instead of three vendor SDKs?
  * keeps the dependency list tiny (httpx only) and install fast,
  * makes the request shape for each provider explicit and auditable,
  * the abstraction is identical to what an SDK would do under the hood.

Each call selects a model *tier* ("fast" or "smart"); config.py maps the tier
to a concrete model per provider. This is what lets the pipeline route cheap
classification to a small model and reply-drafting to a stronger one.
"""
from __future__ import annotations

import json
from typing import Literal, Optional

import httpx

from .config import SETTINGS

Tier = Literal["fast", "smart"]


class LLMClient:
    def __init__(self) -> None:
        self.settings = SETTINGS
        self.cfg = SETTINGS.provider_config  # None in mock mode

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def complete(
        self,
        system: str,
        user: str,
        tier: Tier = "fast",
        max_tokens: int = 700,
        temperature: float = 0.2,
    ) -> str:
        """Return the model's text completion for (system, user)."""
        if self.settings.mock or self.cfg is None:
            return _MockBackend.complete(system, user, tier)

        model = self.cfg.fast_model if tier == "fast" else self.cfg.smart_model
        try:
            if self.cfg.name == "anthropic":
                return self._anthropic(system, user, model, max_tokens, temperature)
            if self.cfg.name == "openai":
                return self._openai(system, user, model, max_tokens, temperature)
            if self.cfg.name == "gemini":
                return self._gemini(system, user, model, max_tokens, temperature)
        except Exception as exc:  # never let a provider hiccup crash the pipeline
            # Graceful degradation: fall back to the deterministic backend so the
            # request still returns something useful, and surface the error inline.
            fallback = _MockBackend.complete(system, user, tier)
            return f"{fallback}\n\n[note: live provider error, used fallback — {exc}]"

        return _MockBackend.complete(system, user, tier)

    # ------------------------------------------------------------------ #
    # Provider adapters                                                  #
    # ------------------------------------------------------------------ #
    def _anthropic(self, system, user, model, max_tokens, temperature) -> str:
        import os

        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()

    def _openai(self, system, user, model, max_tokens, temperature) -> str:
        import os

        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def _gemini(self, system, user, model, max_tokens, temperature) -> str:
        import os

        key = os.environ["GEMINI_API_KEY"]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        resp = httpx.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()


# --------------------------------------------------------------------------- #
# Deterministic offline backend                                               #
# --------------------------------------------------------------------------- #
class _MockBackend:
    """
    Produces plausible, *structured* responses without any network call.

    For classification prompts it returns JSON derived from keyword heuristics.
    For drafting prompts it returns a templated reply that quotes the retrieved
    knowledge-base context that was passed in the user prompt. The goal is a
    realistic end-to-end demo, not a real model.
    """

    @staticmethod
    def complete(system: str, user: str, tier: Tier) -> str:
        is_classification = "JSON" in system and "category" in system.lower()
        if is_classification:
            return _MockBackend._classify(user)
        return _MockBackend._draft(user)

    # -- heuristic classifier ------------------------------------------------ #
    @staticmethod
    def _classify(user: str) -> str:
        import re as _re

        t = user.lower()

        def has(*words):
            # word-boundary match so "down" doesn't fire inside "download", etc.
            return any(_re.search(rf"\b{_re.escape(w)}\b", t) for w in words)

        # Category precedence: most specific / highest-risk first.
        if has("hack", "hacked", "breach", "breached", "phishing", "phish",
               "compromised", "unauthorized", "2fa", "stolen"):
            category = "security"
        elif has("refund", "chargeback") or ("money" in t and "back" in t):
            category = "refund"
        elif has("charge", "charged", "invoice", "billing", "billed",
                 "payment", "subscription", "renewal"):
            category = "billing"
        elif has("error", "errors", "crash", "crashed", "crashing", "broken",
                 "fails", "failing", "bug", "500", "timeout", "timeouts"):
            category = "bug_report"
        elif has("feature", "suggestion", "wish") or ("would be" in t and "great" in t) \
                or ("please" in t and "add" in t):
            category = "feature_request"
        elif has("export", "download", "backup") or "how do i" in t or "how to" in t \
                or "can i" in t or "is it possible" in t or "does it support" in t:
            category = "product_question"
        elif has("login", "log", "password", "reset", "locked", "signin") \
                or ("sign" in t and "in" in t):
            category = "account"
        elif has("api", "webhook", "webhooks", "sdk", "endpoint", "integration"):
            category = "technical"
        else:
            category = "other"

        if has("urgent", "asap", "immediately", "down", "outage", "production") \
                or ("can't" in t and "access" in t) or ("cannot" in t and "access" in t):
            priority = "urgent"
        elif has("soon", "important", "blocked", "deadline"):
            priority = "high"
        elif category in ("feature_request", "product_question"):
            priority = "low"
        else:
            priority = "medium"

        if has("furious", "ridiculous", "unacceptable", "terrible", "worst",
               "angry", "scam") or "fed up" in t:
            sentiment = "angry"
        elif has("frustrated", "frustrating", "annoyed", "annoying", "disappointed") \
                or "still not" in t or "third time" in t:
            sentiment = "frustrated"
        elif has("thanks", "thank", "great", "love", "appreciate", "awesome"):
            sentiment = "positive"
        else:
            sentiment = "neutral"

        confidence = 0.82 if category != "other" else 0.55

        return json.dumps(
            {
                "category": category,
                "priority": priority,
                "sentiment": sentiment,
                "confidence": confidence,
                "reasoning": f"Keyword signals matched category '{category}'.",
            }
        )

    # -- templated reply drafter -------------------------------------------- #
    @staticmethod
    def _draft(user: str) -> str:
        # Pull the KB context the pipeline injected (after the CONTEXT marker)
        # and turn the top snippet into clean, readable sentences.
        context = user.split("CONTEXT:", 1)[1] if "CONTEXT:" in user else ""
        body = ""
        for line in context.splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue
            # line format: "- (KB-009) Title: snippet text…"
            if "): " in line:
                line = line.split("): ", 1)[1]          # drop "(KB-009) "
            if ": " in line:
                line = line.split(": ", 1)[1]            # drop "Title: "
            line = line.replace("…", "").strip()
            if len(line) > 30:
                # keep the first 1-2 sentences for a concise reply
                sentences = line.replace("\n", " ").split(". ")
                body = ". ".join(sentences[:2]).strip()
                if not body.endswith("."):
                    body += "."
                break

        if not body:
            body = (
                "Our team can help with this — could you share a little more detail "
                "so we can point you to the exact steps?"
            )

        return (
            "Hi there,\n\n"
            "Thanks for reaching out. "
            f"{body}\n\n"
            "If that doesn't fully resolve it, just reply here and we'll be glad to help further.\n\n"
            "Best,\nSupport Team"
        )


# Module-level singleton.
llm = LLMClient()
