# Part 1 — AI Research & Evaluation

**Use case chosen: Customer Support Automation.**

The goal is a system that ingests inbound support tickets and, for each one,
(a) classifies it, (b) retrieves relevant knowledge, and (c) decides whether to
auto-resolve, draft a reply for an agent, or escalate to a human. This document
compares the candidate building blocks across three layers — **models**,
**orchestration**, and **retrieval / vector store** — and explains the final
selection.

> All pricing below is **public list pricing as of June 2026** (USD per 1M
> tokens unless noted) and is used only for relative comparison. Vendors change
> prices often — verify on the official pricing pages before committing.

---

## Layer 1 — Foundation models (the "brains")

The system makes two kinds of model calls: a **high-volume classification** call
(every ticket) and a **lower-volume reply-drafting** call (only when we reply).
That split is the single most important cost lever, so each provider is assessed
on both a cheap "fast" tier and a stronger "smart" tier.

### 1.1 Pricing snapshot (June 2026)

| Provider | Fast tier (in / out) | Smart / flagship tier (in / out) | Free tier | Batch | Prompt caching |
|---|---|---|---|---|---|
| **Anthropic (Claude)** | Haiku 4.5 — $1 / $5 | Sonnet 4.6 — $3 / $15 · Opus 4.8 — $15 / $75 | No | −50% | −90% cached input |
| **OpenAI (GPT)** | GPT‑4o mini — $0.15 / $0.60 | GPT‑4o — $2.50 / $10 | No | −50% | −50% cached input |
| **Google (Gemini)** | Gemini 2.0 Flash‑Lite — $0.075 / $0.30 | Gemini 2.5 Pro — $1.25 / $10 (≤200K ctx) | **Yes** (≈1,500 req/day on Flash, no card) | −50% | −75% cached input |

Notes that matter for this use case:
- All three offer ~1M-token context, multimodal input, function/tool calling, JSON-structured output, batch (−50%) and prompt caching (−90% on cached input). For support automation these capabilities are effectively at parity.
- Gemini has by far the cheapest entry point (Flash‑Lite at $0.25/$1.50) and the only meaningful **free tier**, which is attractive for a prototype and for ultra-high-volume classification.
- OpenAI has the broadest model ladder and the largest third-party ecosystem.
- Anthropic's Sonnet 4.6 is widely regarded as the price/quality sweet spot for instruction-following and safe, well-structured customer-facing text, and Claude's tendency toward careful, non-hallucinated output is valuable when replies go to real customers.

### 1.2 Capability / fit comparison

| Criterion | Claude | OpenAI GPT | Gemini |
|---|---|---|---|
| **Instruction following / structured JSON** | Excellent | Excellent | Very good |
| **Quality of customer-facing prose** | Excellent (warm, careful) | Excellent | Very good |
| **Hallucination resistance for RAG** | Strong | Strong | Strong |
| **Cheapest high-volume classification** | Haiku $1/$5 | 4o-mini $0.15/$0.60 | **Flash‑Lite $0.075/$0.30** |
| **Ecosystem / SDK maturity** | Strong | **Broadest** | Strong (Vertex AI) |
| **Free tier for prototyping** | No | No | **Yes** |
| **Best at** | Safe, high-quality replies; agentic tool use | Widest tooling, function calling | Lowest cost at scale, multimodal, GCP-native |
| **Main limitation** | No free tier; premium flagship | Flagship output pricing highest | Flagship slightly behind top rivals on hardest reasoning |

### 1.3 Decision

**Default to Claude (Sonnet 4.6 for drafting, Haiku 4.5 for classification)** for the
quality and safety of customer-facing replies, **but build provider-agnostic** so
OpenAI or Gemini can be swapped via one environment variable. This hedges pricing
and availability risk and lets a team route ultra-high-volume classification to
Gemini Flash‑Lite if cost dominates. The prototype implements exactly this: a
unified client with `fast`/`smart` tiers mapped per provider (see
`app/llm_client.py` and `app/config.py`).

---

## Layer 2 — Orchestration (how the steps are wired together)

| Option | What it is | Pricing | Scalability | Ease of integration | Limitations | Best for |
|---|---|---|---|---|---|---|
| **Custom Python + FastAPI** (chosen) | Hand-written pipeline + REST API | Free (OSS) | Excellent — stateless, horizontally scalable behind a load balancer | High control, minimal deps, trivial to test | You build the plumbing yourself | Teams who want full control, testability, and no vendor lock-in |
| **LangChain / LangGraph** | LLM app framework; chains, agents, memory, retrievers | Free OSS; LangSmith/Platform paid | Good; LangGraph adds durable stateful agents | Many integrations out of the box | Heavy abstraction, fast-moving API, can obscure behavior | Complex multi-step agents, rapid assembly of standard patterns |
| **n8n** | Visual workflow automation (low-code), self-host or cloud | Self-host free; cloud from low monthly tiers | Good for moderate volume; queue mode scales workers | Drag-and-drop, 400+ app nodes, native webhook triggers | Logic-heavy branching is awkward; harder to unit-test | Connecting SaaS tools (Zendesk, Slack, Sheets) with light glue |
| **Make** | Hosted visual automation (operations-priced) | Per-operation pricing | Hosted, scales with plan | Very approachable, large connector library | Per-op cost adds up at volume; cloud-only | Non-engineers automating SaaS workflows |
| **CrewAI** | Multi-agent role/task orchestration | Free OSS | Depends on host | Clean multi-agent abstractions | Newer; overkill for a linear pipeline | Genuinely multi-agent, role-playing workflows |

**Decision:** **Custom Python + FastAPI** for the core engine. The support pipeline
is mostly a linear flow with one branching decision; a framework would add
abstraction and dependency weight without buying much. A small, explicit codebase
is easier to test (see `tests/`), audit, and reason about — and it exposes a clean
REST API that an n8n/Make workflow can call as one node when a team wants to wire
it into Zendesk, Slack, or email. In other words: **code for the intelligence,
low-code for the last-mile integrations.**

---

## Layer 3 — Retrieval / vector store (the "RAG" memory)

| Option | Type | Pricing | Scalability | Ease | Limitations | Best for |
|---|---|---|---|---|---|---|
| **BM25 (in-process)** (chosen for POC) | Lexical ranking, no embeddings | Free | Fine to ~10⁴–10⁵ docs in memory | Zero infra, fully offline, deterministic | No semantic match (synonyms/paraphrase) | Prototypes, small/medium KBs, a strong hybrid component |
| **pgvector (Postgres)** | Vector column in Postgres | Free OSS / managed DB cost | Good into millions with proper indexes | Easy if you already run Postgres | Tuning ANN indexes; not purpose-built | Teams already on Postgres wanting one datastore |
| **Pinecone** | Managed vector DB | Usage/serverless pricing | Excellent, fully managed | Very easy, great DX | Cost at scale; external dependency | Hands-off, large-scale semantic search |
| **Weaviate** | OSS + managed vector DB | OSS free / managed paid | Excellent; hybrid search built-in | Moderate | Operate it yourself if self-hosting | Hybrid (lexical+vector) search, control + scale |

**Decision:** Use **BM25 in-process for the POC** so the prototype runs with zero
external services and is reproducible by an evaluator in one command. BM25 is a
genuinely strong baseline and remains useful in production as the lexical half of
a hybrid retriever. The retriever sits behind a tiny interface (`search(query, k)`
in `app/rag.py`), so the **production upgrade** — embeddings + a vector DB
(pgvector to start, Weaviate/Pinecone at scale), ideally **hybrid BM25 + dense
with reranking** — is a drop-in replacement requiring no change elsewhere in the
pipeline.

---

## Summary of selections

| Layer | Chosen for POC | Production target |
|---|---|---|
| Model — classify | Claude Haiku 4.5 (mock offline by default) | Haiku / Gemini 2.0 Flash‑Lite (cost) |
| Model — draft reply | Claude Sonnet 4.6 | Sonnet 4.6 / GPT‑4o |
| Orchestration | Custom Python + FastAPI | Same + n8n/Make for SaaS last-mile |
| Retrieval | BM25 (in-process) | Hybrid BM25 + embeddings on pgvector → Weaviate/Pinecone |
| Provider strategy | Provider-agnostic, 1 env var to switch | Same, with routing by task |

The guiding principle throughout: **keep the prototype dependency-light, offline,
and testable, while leaving an explicit, low-friction path to a production-grade
system.**
