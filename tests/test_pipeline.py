"""
Test suite for the support-automation pipeline.

Runs entirely in MOCK mode (no API key, no network), so it is deterministic and
CI-friendly. Tests cover the retriever, the classifier output contract, each of
the agent's decision branches, and the full end-to-end pipeline.

Run:  pytest -q
"""
from __future__ import annotations

from app.agent import decide
from app.classifier import classify
from app.pipeline import kb_size, process_ticket
from app.rag import load_retriever
from app.schemas import (
    Action,
    Category,
    Classification,
    Priority,
    RetrievedDoc,
    Sentiment,
    Ticket,
)


# --------------------------------------------------------------------------- #
# Retriever                                                                   #
# --------------------------------------------------------------------------- #
def test_kb_loads():
    assert kb_size() == 12


def test_retriever_finds_relevant_doc():
    r = load_retriever()
    hits = r.search("how do I reset my password", k=3)
    assert hits, "expected at least one hit"
    assert hits[0].doc_id == "KB-001"
    assert 0.0 <= hits[0].score <= 1.0


def test_retriever_scores_are_sorted_desc():
    r = load_retriever()
    hits = r.search("webhook signature verification", k=3)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_retriever_returns_nothing_for_gibberish():
    r = load_retriever()
    assert r.search("zzzzz qqqqq wxyqzv plughxyzzy", k=3) == []


# --------------------------------------------------------------------------- #
# Classifier (contract: always returns valid enums + bounded confidence)      #
# --------------------------------------------------------------------------- #
def test_classifier_contract():
    c = classify(Ticket(subject="I was charged twice", body="explain my billing cycle please"))
    assert isinstance(c.category, Category)
    assert isinstance(c.priority, Priority)
    assert isinstance(c.sentiment, Sentiment)
    assert 0.0 <= c.confidence <= 1.0


def test_classifier_detects_billing():
    c = classify(Ticket(subject="charged twice", body="I see two charges on my invoice this month"))
    assert c.category == Category.BILLING


def test_classifier_detects_angry_sentiment():
    c = classify(Ticket(subject="unacceptable", body="this is ridiculous, absolutely the worst"))
    assert c.sentiment == Sentiment.ANGRY


# --------------------------------------------------------------------------- #
# Agent decision branches                                                     #
# --------------------------------------------------------------------------- #
def _doc(score: float) -> RetrievedDoc:
    return RetrievedDoc(doc_id="KB-X", title="t", snippet="s", score=score)


def test_agent_escalates_security():
    c = Classification(
        category=Category.SECURITY, priority=Priority.MEDIUM,
        sentiment=Sentiment.NEUTRAL, confidence=0.9,
    )
    d = decide(c, [_doc(0.9)])
    assert d.action == Action.ESCALATE
    assert any("human-only" in g for g in d.triggered_guardrails)


def test_agent_escalates_urgent():
    c = Classification(
        category=Category.BUG_REPORT, priority=Priority.URGENT,
        sentiment=Sentiment.NEUTRAL, confidence=0.9,
    )
    d = decide(c, [_doc(0.9)])
    assert d.action == Action.ESCALATE


def test_agent_escalates_on_weak_retrieval():
    c = Classification(
        category=Category.PRODUCT_QUESTION, priority=Priority.LOW,
        sentiment=Sentiment.NEUTRAL, confidence=0.9,
    )
    d = decide(c, [_doc(0.05)])  # below rag_min_score
    assert d.action == Action.ESCALATE


def test_agent_auto_resolves_clean_faq():
    c = Classification(
        category=Category.PRODUCT_QUESTION, priority=Priority.LOW,
        sentiment=Sentiment.NEUTRAL, confidence=0.9,
    )
    d = decide(c, [_doc(0.8)])
    assert d.action == Action.AUTO_RESOLVE
    assert d.requires_human is False


def test_agent_drafts_feature_request():
    c = Classification(
        category=Category.FEATURE_REQUEST, priority=Priority.LOW,
        sentiment=Sentiment.POSITIVE, confidence=0.9,
    )
    d = decide(c, [_doc(0.8)])  # strong match but never auto-resolved
    assert d.action == Action.DRAFT_REPLY


# --------------------------------------------------------------------------- #
# End-to-end                                                                  #
# --------------------------------------------------------------------------- #
def test_end_to_end_escalation_no_draft():
    r = process_ticket(
        Ticket(subject="I think my account was hacked",
               body="my password was changed but it wasn't me")
    )
    assert r.decision.action == Action.ESCALATE
    assert r.draft is None  # we never draft on escalate
    assert r.mode == "mock"


def test_end_to_end_auto_resolve_has_draft_and_citations():
    r = process_ticket(
        Ticket(subject="reset password",
               body="how do I reset my password? I forgot it")
    )
    assert r.draft is not None
    assert r.draft.cited_doc_ids  # grounded in KB
    assert r.latency_ms >= 0
