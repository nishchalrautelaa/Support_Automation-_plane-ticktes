# Architecture & Workflow Diagrams

All diagrams are written in Mermaid and render automatically on GitHub.

## 1. System architecture

```mermaid
flowchart TB
    subgraph Client
        UI["Demo Web UI<br/>(static/index.html)"]
        EXT["External callers<br/>(Zendesk / email / n8n / Slack)"]
    end

    subgraph API["FastAPI service (app/main.py)"]
        EP["/api/process · /api/classify<br/>/api/search · /api/health · /api/samples/"]
    end

    subgraph Pipeline["Pipeline (app/pipeline.py)"]
        direction TB
        C["1 · Classifier<br/>app/classifier.py<br/><i>fast model tier</i>"]
        R["2 · Retriever (RAG)<br/>app/rag.py<br/><i>BM25 over KB</i>"]
        A["3 · Decision Agent<br/>app/agent.py<br/><i>guardrails + policy</i>"]
        G["4 · Responder<br/>app/responder.py<br/><i>smart model tier</i>"]
    end

    subgraph Infra
        LLM["LLM Client<br/>app/llm_client.py<br/>Anthropic | OpenAI | Gemini | MOCK"]
        KB[("Knowledge Base<br/>data/knowledge_base.json")]
    end

    UI --> EP
    EXT --> EP
    EP --> C --> R --> A
    A -->|auto_resolve / draft_reply| G
    A -->|escalate| EP
    G --> EP
    C -. fast .-> LLM
    G -. smart .-> LLM
    R --> KB
```

## 2. Request sequence (one ticket)

```mermaid
sequenceDiagram
    participant U as User / Caller
    participant API as FastAPI
    participant CL as Classifier
    participant RG as Retriever (BM25)
    participant AG as Agent
    participant RS as Responder
    participant M as LLM (fast/smart or mock)

    U->>API: POST /api/process {subject, body}
    API->>CL: classify(ticket)
    CL->>M: fast completion (JSON)
    M-->>CL: category / priority / sentiment / confidence
    API->>RG: search(subject + body, k=3)
    RG-->>API: top-k KB docs + scores
    API->>AG: decide(classification, docs)
    alt guardrail fires OR weak match
        AG-->>API: ESCALATE (no draft)
    else safe + relevant
        AG-->>API: AUTO_RESOLVE or DRAFT_REPLY
        API->>RS: draft_reply(...)
        RS->>M: smart completion (grounded in KB)
        M-->>RS: customer reply text
        RS-->>API: draft + cited doc ids
    end
    API-->>U: ProcessResult (JSON)
```

## 3. Agent decision policy

```mermaid
flowchart TD
    START([classification + retrieved docs]) --> G1{category in<br/>human-only?<br/>security / refund}
    G1 -- yes --> ESC[ESCALATE]
    G1 -- no --> G2{priority<br/>== urgent?}
    G2 -- yes --> ESC
    G2 -- no --> G3{sentiment<br/>== angry?}
    G3 -- yes --> ESC
    G3 -- no --> S1{top retrieval score<br/>&lt; rag_min_score?}
    S1 -- yes --> ESC
    S1 -- no --> S2{confidence ≥ 0.75<br/>AND score ≥ 0.55<br/>AND priority low/med<br/>AND not feature_request?}
    S2 -- yes --> AUTO[AUTO_RESOLVE<br/>reply sent automatically]
    S2 -- no --> DRAFT[DRAFT_REPLY<br/>human reviews & sends]

    classDef esc fill:#3a1d1f,stroke:#e5575f,color:#fff;
    classDef auto fill:#16331f,stroke:#2fbf71,color:#fff;
    classDef draft fill:#33291a,stroke:#e0a23b,color:#fff;
    class ESC esc;
    class AUTO auto;
    class DRAFT draft;
```

**Guardrails-first design:** the three red branches are deterministic and always
win. The system can never auto-send a reply on a security report, a refund
dispute, an urgent ticket, or an angry customer — regardless of model confidence.
Only inside the space the guardrails allow do confidence and retrieval quality
decide how much autonomy to take.

## 4. Production deployment (target)

```mermaid
flowchart LR
    subgraph Sources
        Z[Zendesk / Email / Web form]
    end
    subgraph Edge
        LB[Load balancer]
    end
    subgraph App["Stateless API (N replicas)"]
        F1[FastAPI worker]
        F2[FastAPI worker]
    end
    subgraph Data
        VDB[(pgvector / Weaviate<br/>hybrid retrieval)]
        Q[[Queue<br/>async batch + retries]]
        OBS[Logging / metrics / tracing]
    end
    subgraph Models
        P[LLM provider<br/>Claude / OpenAI / Gemini<br/>+ prompt caching]
    end

    Z --> LB --> F1 & F2
    F1 & F2 --> VDB
    F1 & F2 --> P
    F1 & F2 --> Q
    F1 & F2 --> OBS
```
