# Demo Walkthrough / Video Script

This is a ready-to-record script for a **2–3 minute demo video** plus a list of
the exact screens to capture. Screenshots already live in
[`docs/screenshots/`](screenshots/). To record live, run the app (see below) and
follow the beats.

## Run it (for recording)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

No API key is needed — it runs in **mock mode**. To demo **live** models, add a
key to `.env` (see `.env.example`) and restart; the badge flips to `LIVE`.

---

## Script (≈2.5 min)

**[0:00 — Intro, 20s]**
> "This is an AI customer-support automation system. For every incoming ticket it
> does four things: classifies it, retrieves relevant knowledge-base articles,
> decides what to do, and — only when it's safe — drafts a grounded reply. It's
> built provider-agnostic on Claude, OpenAI, or Gemini, and runs offline in a mock
> mode so you can see the whole pipeline without an API key."

*Show the home screen. Point at the mode badge and the four pipeline tags.*

**[0:20 — Auto-resolve, 35s]**
*Click the sample "How do I export all my data?"*
> "This is a clean FAQ-type question. The classifier tags it as a product question,
> low priority, neutral sentiment, with high confidence. BM25 retrieval pulls up the
> 'Exporting your data' article with a strong score. Because confidence and match
> are both high and there's no risk flag, the agent **auto-resolves** — and drafts a
> reply grounded entirely in that article. Notice the citations at the bottom: the
> answer is traceable to specific KB articles, not invented."

*Point at: classification badges → retrieved docs with score bars → green AUTO-RESOLVE pill → reply + "grounded in" citations.*

**[0:55 — Escalation & guardrails, 35s]**
*Click the sample "This is unacceptable - I want my money back NOW".*
> "Now a refund demand from an angry customer. Watch the agent decision: it
> **escalates** to a human, and it tells you exactly why — three safety guardrails
> fired: refund is a human-only category, the priority read as urgent, and the
> sentiment is angry. Critically, the system **does not draft a reply** here. We
> never put automated words in front of an upset customer about their money — a
> person handles it."

*Point at the red ESCALATE pill and the three guardrail chips, and that the draft section says no reply was drafted.*

**[1:30 — Draft-for-human, 25s]**
*Click the sample "Feature request: dark mode".*
> "A feature request is friendly and low-risk, but it's not something you answer
> from an FAQ — it belongs in a product triage queue. So the agent **drafts a
> courteous reply for a human to review and send** rather than auto-sending. Three
> outcomes, each matched to the situation."

**[1:55 — Under the hood, 30s]**
*Switch to the terminal / API docs at `/docs`.*
> "Under the hood it's a FastAPI service. There's an endpoint for the full pipeline,
> plus granular endpoints to inspect just the classifier or just the retriever. The
> classifier uses a cheap fast model, reply-drafting uses a stronger model — that
> two-tier split is the main cost lever, around half a cent per ticket at scale. The
> retriever is BM25 today behind a tiny interface, so swapping in a vector database
> for production is a drop-in change."

**[2:25 — Close, 10s]**
> "Mock mode for reproducibility, real Claude/OpenAI/Gemini with one environment
> variable, guardrails so automation stays safe, and a clear path to production.
> Thanks for watching."

---

## Screens to capture (for the screenshots deliverable)

| File | What it shows |
|---|---|
| `docs/screenshots/01_home.png` | Landing page, mode badge, input panel, sample tickets |
| `docs/screenshots/02_auto_resolve.png` | Auto-resolve: classification, RAG hits, green decision, grounded reply + Copy button |
| `docs/screenshots/03_escalate.png` | Escalation: red decision pill + three guardrail chips, no draft |
| `docs/screenshots/04_draft_reply.png` | Draft-for-human: amber decision, drafted reply awaiting review |
| `docs/screenshots/05_history.png` | Ticket history panel: last N processed tickets with badges |
| (optional) `/docs` | FastAPI interactive API docs (Swagger UI) |

## Suggested recording tips
- Record at 1280×800 or larger; the UI is responsive.
- Use the sample chips so the demo is fast and deterministic.
- If demoing live mode, do one ticket live to show the `LIVE · <provider>` badge, then continue in mock for speed.
