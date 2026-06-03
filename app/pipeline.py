"""
Pipeline orchestrator.

Runs a ticket through the four stages and returns a single ProcessResult:

    1. classify   (fast model)      -> category / priority / sentiment
    2. retrieve   (BM25 over KB)    -> top-k relevant articles
    3. decide     (policy agent)    -> auto_resolve / draft_reply / escalate
    4. draft      (smart model)     -> grounded reply  [skipped on escalate]

The retriever is built once at import and reused across requests.
"""
from __future__ import annotations

import time

from .agent import decide
from .classifier import classify
from .config import SETTINGS
from .rag import load_retriever
from .responder import draft_reply
from .schemas import Action, ProcessResult, Ticket

_retriever = load_retriever()


def kb_size() -> int:
    return _retriever.N


def process_ticket(ticket: Ticket) -> ProcessResult:
    started = time.time()

    # 1. classify
    classification = classify(ticket)

    # 2. retrieve — query built from subject + body for best recall
    query = f"{ticket.subject} {ticket.body}"
    retrieved = _retriever.search(query, k=SETTINGS.top_k)

    # 3. decide
    decision = decide(classification, retrieved)

    # 4. draft (only when the agent intends to reply)
    draft = None
    if decision.action in (Action.AUTO_RESOLVE, Action.DRAFT_REPLY):
        draft = draft_reply(ticket, classification, retrieved)

    latency_ms = int((time.time() - started) * 1000)

    return ProcessResult(
        ticket=ticket,
        classification=classification,
        retrieved=retrieved,
        decision=decision,
        draft=draft,
        mode=SETTINGS.mode_string,
        latency_ms=latency_ms,
    )
