"""
Reply generator (the "G" in RAG).

Drafts a customer reply with the *smart* model tier, grounded strictly in the
retrieved knowledge-base snippets. The prompt instructs the model to use only
the supplied context and to avoid inventing policy — the standard guardrail
against RAG hallucination. The drafted reply records which KB articles it drew
on so the human reviewer (and the UI) can see the citations.

Only called when the agent chose AUTO_RESOLVE or DRAFT_REPLY — never on an
ESCALATE, where we deliberately do not put words in a human's mouth.
"""
from __future__ import annotations

from typing import List

from .llm_client import llm
from .schemas import Classification, DraftReply, RetrievedDoc, Ticket

_SYSTEM = """You are a helpful, concise customer-support agent. Write a reply to \
the customer using ONLY the knowledge-base context provided. Rules:
- Be warm, direct, and brief (a few short paragraphs at most).
- Use only facts from the context. If the context is insufficient, say you are \
looping in a teammate rather than guessing.
- Do not invent prices, policies, URLs, or commitments.
- Do not mention that you used a "knowledge base" or "context".
- Sign off as "Support Team"."""


def draft_reply(
    ticket: Ticket, classification: Classification, retrieved: List[RetrievedDoc]
) -> DraftReply:
    context_block = "\n".join(
        f"- ({d.doc_id}) {d.title}: {d.snippet}" for d in retrieved
    )
    user = (
        f"Customer subject: {ticket.subject}\n"
        f"Customer message: {ticket.body}\n"
        f"Detected category: {classification.category.value}\n\n"
        f"CONTEXT:\n{context_block}\n\n"
        "Write the reply now."
    )
    text = llm.complete(_SYSTEM, user, tier="smart", max_tokens=500, temperature=0.4)
    return DraftReply(text=text, cited_doc_ids=[d.doc_id for d in retrieved])
