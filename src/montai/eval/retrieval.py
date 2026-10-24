"""Avaliação da busca semântica com recall@k.

recall@k responde: "dos itens que deveriam aparecer, quantos apareceram entre
os k primeiros?". Usamos a versão normalizada, que divide por min(|relevantes|, k):
se a consulta tem 7 itens relevantes e k = 5, acertar 5 já é nota máxima,
porque não cabe mais nada no top 5.

Também medimos o MRR (posição do primeiro acerto), que mostra se o item certo
aparece no topo ou só lá no quinto lugar.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from montai.config import EVAL_DIR
from montai.retrieval import Retriever, SearchFilters

RETRIEVAL_GOLD_PATH = EVAL_DIR / "retrieval.json"


class RetrievalCase(BaseModel):
    id: str
    query: str
    filters: SearchFilters | None = None
    relevant: list[str]


class RetrievalResult(BaseModel):
    id: str
    query: str
    retrieved: list[str]
    relevant: list[str]
    recall: float
    reciprocal_rank: float


class RetrievalReport(BaseModel):
    embedding: str
    k: int
    mean_recall: float
    mrr: float
    results: list[RetrievalResult] = Field(default_factory=list)


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    if not relevant:
        raise ValueError("consulta sem itens relevantes no gabarito")
    hits = len(set(retrieved[:k]) & set(relevant))
    return hits / min(len(relevant), k)


def reciprocal_rank(retrieved: list[str], relevant: list[str]) -> float:
    for position, item_id in enumerate(retrieved, start=1):
        if item_id in relevant:
            return 1 / position
    return 0.0


def load_cases(path: Path = RETRIEVAL_GOLD_PATH) -> list[RetrievalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [RetrievalCase.model_validate(q) for q in data["queries"]]


def evaluate(retriever: Retriever, embedding: str, cases: list[RetrievalCase], k: int = 5) -> RetrievalReport:
    results = []
    for case in cases:
        retrieved = [h.item.id for h in retriever.search(case.query, case.filters, k=k)]
        results.append(RetrievalResult(
            id=case.id,
            query=case.query,
            retrieved=retrieved,
            relevant=case.relevant,
            recall=recall_at_k(retrieved, case.relevant, k),
            reciprocal_rank=reciprocal_rank(retrieved, case.relevant),
        ))
    n = len(results)
    return RetrievalReport(
        embedding=embedding,
        k=k,
        mean_recall=round(sum(r.recall for r in results) / n, 4),
        mrr=round(sum(r.reciprocal_rank for r in results) / n, 4),
        results=results,
    )
