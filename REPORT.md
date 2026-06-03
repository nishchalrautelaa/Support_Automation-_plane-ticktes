# Part 3 — Recommendation Report

## 1. Recommended architecture

A **stateless FastAPI service** runs a four-stage pipeline per ticket:

1. **Classify** with a small/fast model → `category`, `priority`, `sentiment`, `confidence`.
2. **Retrieve** the top-k knowledge-base articles (BM25 in the POC; hybrid BM25 + embeddings in production).
3. **Decide** with a guardrails-first policy agent → `auto_resolve`, `draft_reply`, or `escalate`.
4. **Draft** a reply with a stronger model, **grounded only in retrieved KB content**, and only when the agent chose to reply.

The model layer is **provider-agnostic** (Anthropic / OpenAI / Gemini) behind a
single client with `fast` and `smart` tiers, selectable with one environment
variable. With no key present the system runs fully offline in **mock mode**, so
the pipeline and demo are reproducible at zero cost. See
[`docs/architecture.md`](architecture.md) for diagrams.

## 2. Why these tools/models

| Decision | Choice | Reasoning |
|---|---|---|
| Reply model | **Claude Sonnet 4.6** | Best balance of quality, instruction-following, and safe, hallucination-resistant customer-facing prose at $3/$15. |
| Classifier model | **Claude Haiku 4.5** (or Gemini 2.0 Flash‑Lite) | Classification is high-volume and easy; a cheap model is the #1 cost lever. Flash‑Lite ($0.075/$0.30) is the budget option. |
| Provider strategy | **Agnostic, 1-var switch** | Hedges price/availability risk; lets teams route ultra-high-volume classification to the cheapest provider. |
| Orchestration | **Custom Python + FastAPI** | The flow is mostly linear with one branch; a framework adds abstraction/weight without payoff. Clean REST API integrates with n8n/Make for SaaS last-mile. |
| Retrieval (POC) | **BM25 in-process** | Strong baseline, zero infra, fully offline and reproducible; also the lexical half of a production hybrid retriever. |
| Retrieval (prod) | **Hybrid BM25 + embeddings on pgvector → Weaviate/Pinecone** | Adds semantic matching (synonyms/paraphrase) while keeping lexical precision; drop-in behind the existing `search()` interface. |
| Safety model | **Guardrails-first agent** | Deterministic rules prevent auto-replies on security, refunds, urgent, or angry tickets — autonomy only where it's safe. |

## 3. Estimated infrastructure cost

**Per-ticket model cost** (live mode, Claude Haiku classify + Sonnet draft),
based on typical token counts:

| Stage | Model | Tokens (in / out) | Cost / call |
|---|---|---|---|
| Classify (every ticket) | Haiku 4.5 ($1 / $5) | ~450 / ~80 | ~$0.0009 |
| Draft (≈60% of tickets¹) | Sonnet 4.6 ($3 / $15) | ~950 / ~250 | ~$0.0066 |

¹ Assumes ~40% of tickets escalate (no draft). **Blended ≈ $0.0009 + 0.6 × $0.0066 ≈ $0.005 / ticket.**

**Monthly totals by volume** (LLM spend; before prompt-caching discounts):

| Tickets / month | LLM cost (~$0.005 ea) | With caching² | Hosting³ | Vector DB⁴ | **All-in estimate** |
|---|---|---|---|---|---|
| 1,000 | ~$5 | ~$3 | ~$5–10 | $0 (free tier) | **~$10–20** |
| 10,000 | ~$50 | ~$30 | ~$15–25 | $0–20 | **~$50–90** |
| 100,000 | ~$500 | ~$300 | ~$50–100 | ~$20–70 | **~$400–500** |

² Prompt caching (−90% on cached input) on the shared system prompts meaningfully cuts input cost; the figure is approximate.
³ Small container (1 vCPU / 1–2 GB) on Fly.io / Render / Railway, scaled by replicas.
⁴ pgvector on a managed Postgres free/low tier at small scale; Pinecone/Weaviate serverless as volume grows.

**Takeaway:** even at 100K tickets/month the system runs for roughly the cost of
**a fraction of one support agent's salary**, and model cost dominates only
modestly. Batch mode (−50%) further cuts cost for any non-real-time queue.

## 4. Risks & limitations

| Risk | Mitigation |
|---|---|
| **Hallucinated or wrong answers** to customers | Replies grounded strictly in retrieved KB; prompt forbids inventing policy; guardrails route low-confidence/low-match tickets to humans; auto-resolve bar is conservative. |
| **Mis-classification** (e.g. missing an angry/security ticket) | Cheap to run a stronger classifier; sentiment + category guardrails are conservative (err toward escalation); add human spot-checks and feedback loop. |
| **BM25 misses semantic matches** (synonyms/paraphrase) | POC limitation by design; production uses hybrid lexical + embedding retrieval with reranking. |
| **Stale knowledge base** | KB is the single source of truth; add a re-index step on KB update; surface "last updated" and low-coverage gaps. |
| **Provider outage / price change** | Provider-agnostic client with graceful fallback; can switch with one env var; batch/caching to control cost. |
| **Prompt injection via ticket text** | Treat ticket content as untrusted data, never as instructions; keep the model's role/system prompt fixed; never let ticket text trigger actions (sends, refunds) without human approval. |
| **PII / privacy** | Use providers with no-training data terms; redact/avoid logging PII; restrict data retention; regional hosting if required. |
| **Over-automation eroding CX** | Keep humans in the loop for anything sensitive; track CSAT on auto-resolved tickets; allow easy "this didn't help → human" path. |

## 5. Scaling to production

- **Horizontal scale:** the API is stateless — run N replicas behind a load balancer; throughput scales linearly. The KB/retriever moves out of process into a vector DB shared by all replicas.
- **Throughput & cost:** push non-real-time tickets through a **queue** and the **batch API (−50%)**; enable **prompt caching (−90% input)** on the shared system prompts.
- **Retrieval upgrade:** swap BM25 for **hybrid BM25 + embeddings** (pgvector first, Weaviate/Pinecone at large scale) with a reranking step — no pipeline changes thanks to the `search()` interface.
- **Integrations (last-mile):** expose the existing REST API as a single node in **n8n / Make** to connect Zendesk, Freshdesk, email, or Slack; the engine stays in code, the connectors stay low-code.
- **Observability & quality:** add structured logging, per-stage latency metrics, and tracing; capture agent decisions and citations for audit; build a **feedback loop** where human edits to drafts and CSAT scores tune thresholds and improve the KB.
- **Continuous evaluation:** maintain a labelled ticket set (the `tests/` + sample tickets are the seed) and run it on every change to catch classification/decision regressions before deploy.
- **Governance:** start with a **high human-review ratio**, then raise the auto-resolve threshold only for categories with proven high CSAT and low correction rates.

## 6. Bonus criteria addressed

- **AI agent** — guardrails-first decision agent (`app/agent.py`).
- **RAG system** — BM25 retrieval + grounded generation (`app/rag.py`, `app/responder.py`).
- **Multi-model workflow** — fast tier for classify, smart tier for drafting (`app/config.py`).
- **Real API integrations** — live adapters for Anthropic, OpenAI, and Gemini (`app/llm_client.py`).
- **Cost optimization analysis** — two-tier routing, batch, caching, this section.
- **Production deployment thinking** — sections 4–5 and the deployment diagram.
