"""
Central configuration for the support-automation system.

The system runs in one of two modes, decided automatically at startup:

  * LIVE  — if an API key for a supported provider is found in the environment,
            real model calls are made. Provider preference order is
            Anthropic -> OpenAI -> Gemini, overridable with LLM_PROVIDER.

  * MOCK  — if no key is present, deterministic offline stand-ins are used for
            every LLM call so the full pipeline (and the demo UI) still runs.
            This keeps the prototype reproducible and free to evaluate.

Each provider exposes a "fast" tier (cheap, used for classification/routing)
and a "smart" tier (higher quality, used for drafting customer replies). This
two-tier split is the core cost-optimization lever — see REPORT.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional
    pass


@dataclass
class ProviderConfig:
    name: str
    api_key_env: str
    fast_model: str
    smart_model: str
    # cost per million tokens (input, output) for the chosen models — June 2026 rates,
    # used by the /process endpoint to estimate per-ticket cost.
    fast_cost_in_out: tuple = (0.0, 0.0)
    smart_cost_in_out: tuple = (0.0, 0.0)


# Current-generation models + public API pricing (USD / 1M tokens).
PROVIDERS: Dict[str, ProviderConfig] = {
    "anthropic": ProviderConfig(
        name="anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        fast_model="claude-haiku-4-5-20251001",  # $1 in / $5 out
        smart_model="claude-sonnet-4-6",         # $3 in / $15 out
        fast_cost_in_out=(1.0, 5.0),
        smart_cost_in_out=(3.0, 15.0),
    ),
    "openai": ProviderConfig(
        name="openai",
        api_key_env="OPENAI_API_KEY",
        fast_model="gpt-4o-mini",           # $0.15 in / $0.60 out
        smart_model="gpt-4o",               # $2.50 in / $10 out
        fast_cost_in_out=(0.15, 0.60),
        smart_cost_in_out=(2.5, 10.0),
    ),
    "gemini": ProviderConfig(
        name="gemini",
        api_key_env="GEMINI_API_KEY",
        fast_model="gemini-2.0-flash-lite",  # $0.075 in / $0.30 out
        smart_model="gemini-2.5-pro",        # $1.25 in / $10 out
        fast_cost_in_out=(0.075, 0.30),
        smart_cost_in_out=(1.25, 10.0),
    ),
}

PROVIDER_PREFERENCE = ["anthropic", "openai", "gemini"]


@dataclass
class Settings:
    # --- agent / routing thresholds (tunable without touching code logic) --- #
    # Minimum top retrieval score (normalized 0-1) to trust the knowledge base.
    rag_min_score: float = 0.18
    # Classification confidence required before any automated action.
    min_confidence_auto: float = 0.75
    # Retrieval score above which a high-confidence FAQ may be auto-resolved.
    auto_resolve_score: float = 0.55
    # Number of KB docs to retrieve per ticket.
    top_k: int = 3

    # Categories that must always go to a human regardless of confidence.
    human_only_categories: tuple = ("security", "refund")

    # Categories that may be answered but never auto-sent (always drafted for a
    # human, e.g. feature requests belong in a product triage queue, not an
    # automated FAQ reply).
    no_auto_resolve_categories: tuple = ("feature_request",)

    provider: Optional[str] = None
    mock: bool = True
    _resolved_provider: Optional[ProviderConfig] = field(default=None, repr=False)

    def resolve(self) -> "Settings":
        """Decide LIVE vs MOCK and which provider to use."""
        forced = os.getenv("LLM_PROVIDER", "").strip().lower()
        order = [forced] if forced in PROVIDERS else PROVIDER_PREFERENCE

        for name in order:
            cfg = PROVIDERS[name]
            if os.getenv(cfg.api_key_env):
                self.provider = name
                self._resolved_provider = cfg
                self.mock = False
                return self

        # No key found anywhere -> mock mode.
        self.provider = "mock"
        self.mock = True
        self._resolved_provider = None
        return self

    @property
    def provider_config(self) -> Optional[ProviderConfig]:
        return self._resolved_provider

    @property
    def mode_string(self) -> str:
        return "mock" if self.mock else f"live:{self.provider}"


SETTINGS = Settings().resolve()
