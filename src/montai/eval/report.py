"""Agrega as métricas por versão e escreve o relatório comparativo."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean, median

from pydantic import BaseModel

from montai.eval.metrics import METRICS, CaseScore, EvalCase, score_case
from montai.eval.runner import RunRecord
from montai.models import Catalog

METRIC_LABELS = {
    "classification_ok": "Classificou possível/impossível certo",
    "budget_ok": "Respeitou o orçamento",
    "diet_ok": "Respeitou as restrições",
    "quantity_ok": "Quantidade adequada às pessoas",
    "catalog_ok": "Todos os itens existem no catálogo",
    "success": "Pedido resolvido por completo",
}
GROUP_LABELS = {
    "ocasiao": "Ocasiões variadas",
    "orcamento_apertado": "Orçamento apertado",
    "restricoes_combinadas": "Restrições combinadas",
    "impossivel": "Impossíveis",
    "ambiguo": "Ambíguos",
}


# Uma chamada que levou mais que isso (fora as esperas registradas) ficou presa
# no provedor até o timeout: não é tempo do modelo nem do nosso código.
STALL_MS = 5 * 60 * 1000


class Rate(BaseModel):
    ok: int
    n: int

    @property
    def value(self) -> float | None:
        return self.ok / self.n if self.n else None

    def fmt(self) -> str:
        return "n/a" if not self.n else f"{100 * self.ok / self.n:.0f}% ({self.ok}/{self.n})"


class VersionSummary(BaseModel):
    version: str
    model: str
    cases: int
    rates: dict[str, Rate]
    success_by_group: dict[str, Rate]
    mean_tokens: float
    mean_llm_calls: float
    mean_latency_s: float
    median_latency_s: float
    mean_net_latency_s: float
    median_net_latency_s: float
    stalled_runs: int  # execuções com uma chamada presa > 5 min no provedor (timeout)
    mean_cost_usd: float
    total_cost_usd: float


def rate(scores: list[CaseScore], metric: str) -> Rate:
    values = [getattr(s, metric) for s in scores if getattr(s, metric) is not None]
    return Rate(ok=sum(values), n=len(values))


def summarize(
    version: str, records: dict[str, RunRecord], cases: list[EvalCase], catalog: Catalog
) -> tuple[VersionSummary, list[CaseScore]]:
    ran = [c for c in cases if c.id in records]
    scores = [score_case(c, records[c.id].cart, catalog) for c in ran]
    traces = [records[c.id].trace for c in ran]

    by_group: dict[str, list[CaseScore]] = defaultdict(list)
    for s in scores:
        by_group[s.group].append(s)

    latencies = [t.latency_ms / 1000 for t in traces]
    summary = VersionSummary(
        version=version,
        model=records[ran[0].id].model if ran else "",
        cases=len(ran),
        rates={m: rate(scores, m) for m in METRICS},
        success_by_group={g: rate(by_group[g], "success") for g in GROUP_LABELS if g in by_group},
        mean_tokens=mean(t.tokens_in + t.tokens_out for t in traces) if traces else 0,
        mean_llm_calls=mean(t.llm_calls for t in traces) if traces else 0,
        mean_latency_s=mean(latencies) if traces else 0,
        median_latency_s=median(latencies) if traces else 0,
        mean_net_latency_s=mean(t.net_latency_ms / 1000 for t in traces) if traces else 0,
        median_net_latency_s=median(t.net_latency_ms / 1000 for t in traces) if traces else 0,
        stalled_runs=sum(
            any(s.latency_ms - s.wait_ms > STALL_MS for s in t.steps) for t in traces
        ),
        mean_cost_usd=mean(t.cost_usd for t in traces) if traces else 0,
        total_cost_usd=sum(t.cost_usd for t in traces),
    )
    return summary, scores


def _mark(score: CaseScore | None) -> str:
    if score is None:
        return "-"
    return f"{'✅' if score.success else '❌'} {score.status.value}"


def to_markdown(
    summaries: list[VersionSummary], scores: dict[str, list[CaseScore]], cases: list[EvalCase], scope: str
) -> str:
    versions = [s.version for s in summaries]
    header = "| | " + " | ".join(f"Versão {v}" for v in versions) + " |"
    sep = "|---" * (len(versions) + 1) + "|"

    out = ["# Avaliação do Montaí", ""]
    out.append(
        f"Pedidos de teste em `data/eval/orders.json`. {scope} "
        + ", ".join(f"Versão {s.version}: {s.cases} executados ({s.model})" for s in summaries)
        + "."
    )
    out += ["", "## Taxa de acerto por métrica", "", header, sep]
    for metric in METRICS:
        row = " | ".join(s.rates[metric].fmt() for s in summaries)
        out.append(f"| {METRIC_LABELS[metric]} | {row} |")
    out += [
        "",
        ("Orçamento, restrições, quantidade e catálogo são medidos só nos pedidos em que um carrinho "
        "foi entregue; restrições, só nos pedidos que têm alguma."),
        "",
        "## Custo e desempenho (média por pedido)",
        "",
        header,
        sep,
        "| Tokens (entrada + saída) | " + " | ".join(f"{s.mean_tokens:,.0f}" for s in summaries) + " |",
        "| Chamadas ao LLM | " + " | ".join(f"{s.mean_llm_calls:.1f}" for s in summaries) + " |",
        "| **Latência líquida, mediana (s)** | "
        + " | ".join(f"**{s.median_net_latency_s:.1f}**" for s in summaries) + " |",
        "| Latência líquida, média (s) | " + " | ".join(f"{s.mean_net_latency_s:.1f}" for s in summaries) + " |",
        "| Latência total com esperas, mediana (s) | "
        + " | ".join(f"{s.median_latency_s:.1f}" for s in summaries) + " |",
        "| Execuções com chamada presa no provedor | " + " | ".join(str(s.stalled_runs) for s in summaries) + " |",
        "| Custo estimado (US$) | " + " | ".join(f"{s.mean_cost_usd:.5f}" for s in summaries) + " |",
        "",
        ("Latência líquida = tempo total menos as esperas por limite de taxa do plano gratuito. "
        "A mediana é a medida principal: algumas chamadas ficaram presas no provedor até o timeout "
        "(cerca de 10 min) antes de serem reenviadas, e esses casos distorcem a média."),
        "",
        "## Pedidos resolvidos por grupo",
        "",
        header,
        sep,
    ]
    for group, label in GROUP_LABELS.items():
        cells = [s.success_by_group[group].fmt() if group in s.success_by_group else "n/a" for s in summaries]
        out.append(f"| {label} | {' | '.join(cells)} |")

    index = {v: {s.case_id: s for s in scores[v]} for v in versions}
    out += ["", "## Resultado por pedido", "", "| Pedido | " + " | ".join(versions) + " |", sep]
    for case in cases:
        cells = " | ".join(_mark(index[v].get(case.id)) for v in versions)
        out.append(f"| {case.id}: {case.order} | {cells} |")

    out += ["", "## Falhas", ""]
    for v in versions:
        failures = [s for s in scores[v] if not s.success]
        out.append(f"**Versão {v}** ({len(failures)})")
        out.append("")
        if not failures:
            out.append("- nenhuma")
        for s in failures:
            order = next(c.order for c in cases if c.id == s.case_id)
            detail = "; ".join(s.notes) if s.notes else f"status {s.status.value}"
            out.append(f"- {s.case_id} ({order}): {detail}")
        out.append("")
    return "\n".join(out)
