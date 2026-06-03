"""
Pydantic data models shared across the support-automation pipeline.

These models define the contract between every stage of the workflow:
    Ticket -> Classification -> Retrieval -> AgentDecision -> DraftReply -> ProcessResult
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums (closed vocabularies so downstream logic is deterministic)            #
# --------------------------------------------------------------------------- #
class Category(str, Enum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    PRODUCT_QUESTION = "product_question"
    REFUND = "refund"
    BUG_REPORT = "bug_report"
    FEATURE_REQUEST = "feature_request"
    SECURITY = "security"
    OTHER = "other"


class Priority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Sentiment(str, Enum):
    ANGRY = "angry"
    FRUSTRATED = "frustrated"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


class Action(str, Enum):
    """The three actions the decision agent can take."""
    AUTO_RESOLVE = "auto_resolve"   # high-confidence FAQ: send the drafted answer automatically
    DRAFT_REPLY = "draft_reply"     # draft a reply, route to a human agent for one-click send
    ESCALATE = "escalate"           # hand to a specialist / senior agent, no auto-draft sent


# --------------------------------------------------------------------------- #
# Pipeline models                                                             #
# --------------------------------------------------------------------------- #
class Ticket(BaseModel):
    id: Optional[str] = Field(default=None, description="External ticket id, if any")
    subject: str = Field(..., description="Short subject line of the ticket")
    body: str = Field(..., description="Full body text written by the customer")
    customer_email: Optional[str] = None
    customer_plan: Optional[str] = Field(
        default=None, description="e.g. free / pro / enterprise — used by routing policy"
    )


class Classification(BaseModel):
    category: Category
    priority: Priority
    sentiment: Sentiment
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence 0-1")
    reasoning: str = Field(default="", description="One-line justification from the model")


class RetrievedDoc(BaseModel):
    doc_id: str
    title: str
    snippet: str
    score: float = Field(..., description="Relevance score from the retriever (BM25)")


class AgentDecision(BaseModel):
    action: Action
    rationale: str = Field(..., description="Why the agent chose this action")
    triggered_guardrails: List[str] = Field(
        default_factory=list, description="Names of any safety guardrails that fired"
    )
    requires_human: bool = Field(
        default=True, description="True unless the answer was auto-sent"
    )


class DraftReply(BaseModel):
    text: str
    cited_doc_ids: List[str] = Field(default_factory=list)


class ProcessResult(BaseModel):
    """The full output of running one ticket through the pipeline."""
    ticket: Ticket
    classification: Classification
    retrieved: List[RetrievedDoc]
    decision: AgentDecision
    draft: Optional[DraftReply] = None
    mode: str = Field(..., description="'live:<provider>' or 'mock'")
    latency_ms: int = 0


# --------------------------------------------------------------------------- #
# API request/response wrappers                                               #
# --------------------------------------------------------------------------- #
class ProcessRequest(BaseModel):
    subject: str
    body: str
    customer_email: Optional[str] = None
    customer_plan: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    mode: str
    provider: str
    kb_articles: int
