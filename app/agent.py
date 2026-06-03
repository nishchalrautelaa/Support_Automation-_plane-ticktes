"""
Decision agent.

Given the classification and the retrieved knowledge-base hits, the agent
chooses one of three actions: AUTO_RESOLVE, DRAFT_REPLY, or ESCALATE.

Design choice — *guardrails first, then confidence*:
A pure-LLM "do whatever seems right" agent is risky for customer-facing
automation. Instead the agent layers deterministic safety guardrails on top of
the model's classification. Guardrails always win, so the system can never, for
example, auto-send a reply on a security report or a refund dispute. Within the
space the guardrails allow, confidence and retrieval quality decide how much
autonomy to take. This is an "agent" in the practical sense — it reasons over
multiple signals and selects an action/tool — while staying auditable.

Every decision returns a rationale and the list of guardrails that fired, so
the behaviour is fully explainable in the UI and in logs.
"""
from __future__ import annotations

from typing import List

from .config import SETTINGS
from .schemas import (
    Action,
    AgentDecision,
    Classification,
    Priority,
    RetrievedDoc,
    Sentiment,
)


def decide(classification: Classification, retrieved: List[RetrievedDoc]) -> AgentDecision:
    s = SETTINGS
    guardrails: List[str] = []
    top_score = retrieved[0].score if retrieved else 0.0

    # ---- Hard guardrails: these force ESCALATE no matter what ------------- #
    if classification.category.value in s.human_only_categories:
        guardrails.append(f"category '{classification.category.value}' is human-only")

    if classification.priority == Priority.URGENT:
        guardrails.append("urgent priority requires a human")

    if classification.sentiment == Sentiment.ANGRY:
        guardrails.append("angry sentiment requires a human touch")

    if guardrails:
        return AgentDecision(
            action=Action.ESCALATE,
            rationale=(
                "Escalated to a human agent because one or more safety guardrails "
                "fired. No automated reply was sent."
            ),
            triggered_guardrails=guardrails,
            requires_human=True,
        )

    # ---- Soft signals: decide level of autonomy --------------------------- #
    # Weak knowledge-base support -> we don't trust an automated answer.
    if top_score < s.rag_min_score or not retrieved:
        return AgentDecision(
            action=Action.ESCALATE,
            rationale=(
                "Escalated: no sufficiently relevant knowledge-base article was "
                f"found (top score {top_score:.2f} < {s.rag_min_score})."
            ),
            triggered_guardrails=[],
            requires_human=True,
        )

    # Strong match + high classification confidence + low-risk -> auto-resolve.
    if (
        classification.confidence >= s.min_confidence_auto
        and top_score >= s.auto_resolve_score
        and classification.priority in (Priority.LOW, Priority.MEDIUM)
        and classification.category.value not in s.no_auto_resolve_categories
    ):
        return AgentDecision(
            action=Action.AUTO_RESOLVE,
            rationale=(
                "Auto-resolved: high classification confidence "
                f"({classification.confidence:.2f}) and a strong KB match "
                f"(score {top_score:.2f}). Reply sent automatically."
            ),
            triggered_guardrails=[],
            requires_human=False,
        )

    # Default: draft a reply for a human to review and send with one click.
    return AgentDecision(
        action=Action.DRAFT_REPLY,
        rationale=(
            "Drafted a reply for human review: relevant KB content was found "
            f"(score {top_score:.2f}) but confidence/risk did not meet the "
            "auto-resolve bar."
        ),
        triggered_guardrails=[],
        requires_human=True,
    )
