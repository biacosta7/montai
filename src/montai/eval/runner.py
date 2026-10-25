"""Executa os pedidos de teste em cada versão e guarda o resultado bruto.

Cada execução vira um arquivo reports/runs/<versão>/<id>.json com o carrinho,
a especificação (quando houver) e o trace completo. Os arquivos são
versionados: os números do relatório podem ser conferidos e recalculados sem
chamar o modelo de novo. Também permitem retomar uma avaliação interrompida
pela cota diária do plano gratuito.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from montai.agent_single.agent import run_agent
from montai.config import REPORTS_DIR
from montai.llm import LLMClient
from montai.models import Cart, Catalog
from montai.pipeline.orchestrator import run_pipeline
from montai.retrieval import Retriever
from montai.tracing import Trace

RUNS_DIR = REPORTS_DIR / "runs"


class RunRecord(BaseModel):
    case_id: str
    version: str
    model: str
    order: str
    finished_at: str
    cart: Cart
    spec: dict | None = None
    trace: Trace


class RunOutput(BaseModel):
    cart: Cart
    trace: Trace
    spec: dict | None = None


Runner = Callable[[str], RunOutput]


def make_runners(llm: LLMClient, retriever: Retriever, catalog: Catalog) -> dict[str, Runner]:
    def run_b(order: str) -> RunOutput:
        result = run_pipeline(order, llm=llm, retriever=retriever, catalog=catalog)
        spec = result.spec.model_dump(mode="json") if result.spec else None
        return RunOutput(cart=result.cart, trace=result.trace, spec=spec)

    def run_a(order: str) -> RunOutput:
        result = run_agent(order, llm=llm, retriever=retriever, catalog=catalog)
        return RunOutput(cart=result.cart, trace=result.trace)

    return {"A": run_a, "B": run_b}


def record_path(version: str, case_id: str, runs_dir: Path = RUNS_DIR) -> Path:
    return runs_dir / version / f"{case_id}.json"


def save_record(record: RunRecord, runs_dir: Path = RUNS_DIR) -> None:
    path = record_path(record.version, record.case_id, runs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")


def load_records(version: str, runs_dir: Path = RUNS_DIR) -> dict[str, RunRecord]:
    folder = runs_dir / version
    if not folder.exists():
        return {}
    records = [RunRecord.model_validate_json(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")]
    return {r.case_id: r for r in records}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
