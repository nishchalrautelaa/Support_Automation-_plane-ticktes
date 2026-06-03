"""
Retrieval layer for the RAG pipeline.

Implements BM25 (Okapi) ranking in pure Python over the JSON knowledge base.
BM25 is a strong, well-understood lexical baseline that needs zero external
services or embedding API calls, which keeps the prototype fully offline and
reproducible.

Production upgrade path (see REPORT.md):
    The `Retriever` interface below is deliberately small — `search(query, k)`.
    Swapping BM25 for a vector store (Pinecone / Weaviate / pgvector) means
    implementing the same interface with an embedding model + ANN search, with
    no change required anywhere else in the pipeline. A hybrid (BM25 + dense)
    reranked retriever is the recommended production target.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import List

from .schemas import RetrievedDoc

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "it",
    "i", "you", "my", "me", "we", "this", "that", "with", "how", "do", "can",
    "be", "are", "as", "at", "by", "if", "so", "not", "no", "but", "your",
}


def _tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP and len(t) > 1]


class BM25Retriever:
    """Okapi BM25 over a list of {id, title, content, tags} documents."""

    def __init__(self, docs: List[dict], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs = docs
        # Index title twice to weight it more heavily than body text.
        self.corpus_tokens = [
            _tokenize(d["title"]) * 2
            + _tokenize(d["content"])
            + _tokenize(" ".join(d.get("tags", [])))
            for d in docs
        ]
        self.doc_len = [len(toks) for toks in self.corpus_tokens]
        self.avgdl = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        self.N = len(docs)
        self.df: Counter = Counter()
        for toks in self.corpus_tokens:
            for term in set(toks):
                self.df[term] += 1
        self.tf = [Counter(toks) for toks in self.corpus_tokens]

    def _idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        # BM25 idf with +1 smoothing to keep it non-negative.
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def _score(self, query_tokens: List[str], idx: int) -> float:
        score = 0.0
        tf = self.tf[idx]
        dl = self.doc_len[idx]
        for term in query_tokens:
            if term not in tf:
                continue
            idf = self._idf(term)
            freq = tf[term]
            denom = freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
            score += idf * (freq * (self.k1 + 1)) / (denom or 1)
        return score

    def search(self, query: str, k: int = 3) -> List[RetrievedDoc]:
        q = _tokenize(query)
        if not q:
            return []
        raw = [(i, self._score(q, i)) for i in range(self.N)]
        raw = [r for r in raw if r[1] > 0]
        raw.sort(key=lambda x: x[1], reverse=True)
        top = raw[:k]
        if not top:
            return []
        # Map raw BM25 score to an absolute-ish 0-1 relevance with a saturating
        # transform:  norm = raw / (raw + K).  Unlike normalizing against the
        # best hit, this preserves *absolute* match quality, so the agent's
        # thresholds (rag_min_score, auto_resolve_score) stay meaningful: a
        # strong match lands ~0.65-0.8, a weak/spurious one ~0.25-0.45.
        K = 4.0
        results: List[RetrievedDoc] = []
        for idx, sc in top:
            d = self.docs[idx]
            content = d["content"]
            snippet = content[:240] + ("…" if len(content) > 240 else "")
            results.append(
                RetrievedDoc(
                    doc_id=d["id"],
                    title=d["title"],
                    snippet=snippet,
                    score=round(sc / (sc + K), 3),
                )
            )
        return results


def load_retriever(kb_path: str | Path | None = None) -> BM25Retriever:
    if kb_path is None:
        kb_path = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"
    with open(kb_path, "r", encoding="utf-8") as fh:
        docs = json.load(fh)
    return BM25Retriever(docs)
