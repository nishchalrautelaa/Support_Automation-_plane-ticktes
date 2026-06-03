"""
FastAPI entry point for the AI Customer-Support Automation prototype.

Endpoints
---------
GET  /                     -> demo web UI (static/index.html)
GET  /api/health           -> mode (mock/live), provider, KB size
GET  /api/samples          -> example tickets to try in the UI
POST /api/process          -> run the full pipeline on one ticket
POST /api/batch            -> run the pipeline on a list of tickets (max 20)
POST /api/classify         -> classification stage only (for granular demos)
GET  /api/search?q=...     -> retrieval stage only (inspect the RAG layer)

Run:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .classifier import classify
from .config import SETTINGS
from .pipeline import kb_size, process_ticket, _retriever
from .schemas import HealthResponse, ProcessRequest, Ticket

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"

app = FastAPI(
    title="AI Customer-Support Automation",
    description="Classify → Retrieve (RAG) → Agent decision → Draft reply. "
    "Runs in mock mode with no API key, or live with Anthropic/OpenAI/Gemini.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def home():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"message": "UI not found. See /docs for the API."})


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        mode=SETTINGS.mode_string,
        provider=SETTINGS.provider or "mock",
        kb_articles=kb_size(),
    )


@app.get("/api/samples")
def samples():
    path = DATA_DIR / "sample_tickets.json"
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@app.post("/api/process")
def process(req: ProcessRequest):
    ticket = Ticket(
        subject=req.subject,
        body=req.body,
        customer_email=req.customer_email,
        customer_plan=req.customer_plan,
    )
    result = process_ticket(ticket)
    return json.loads(result.model_dump_json())


@app.post("/api/batch")
def batch_process(reqs: List[ProcessRequest]):
    if len(reqs) > 20:
        raise HTTPException(status_code=422, detail="Batch size limit is 20 tickets.")
    results = []
    for req in reqs:
        ticket = Ticket(
            subject=req.subject,
            body=req.body,
            customer_email=req.customer_email,
            customer_plan=req.customer_plan,
        )
        results.append(json.loads(process_ticket(ticket).model_dump_json()))
    return results


@app.post("/api/classify")
def classify_only(req: ProcessRequest):
    ticket = Ticket(subject=req.subject, body=req.body)
    return json.loads(classify(ticket).model_dump_json())


@app.get("/api/search")
def search_only(q: str = Query(..., description="Search query against the knowledge base")):
    hits = _retriever.search(q, k=SETTINGS.top_k)
    return [json.loads(h.model_dump_json()) for h in hits]


# Serve any other static assets (kept last so it doesn't shadow API routes).
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
