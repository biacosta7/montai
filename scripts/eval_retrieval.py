"""Mede recall@5 e MRR da busca em cada configuração (modelo x texto do documento).

É um experimento de ablação: muda uma coisa por vez para saber o que
realmente melhora a busca.

Uso: python scripts/eval_retrieval.py [--k 5]
Saída: tabela no terminal + reports/retrieval.md e reports/retrieval.json
"""

from __future__ import annotations

import argparse
import json

from montai.catalog import load_catalog
from montai.config import REPORTS_DIR
from montai.eval.retrieval import RetrievalReport, evaluate, load_cases
from montai.retrieval import Retriever

# (rótulo, modelo de embeddings, texto enriquecido com dieta e picância?)
CONFIGS = [
    ("minilm", "minilm", False),
    ("e5-small", "e5-small", False),
    ("minilm + atributos", "minilm", True),
    ("e5-small + atributos", "e5-small", True),
]


def to_markdown(reports: list[RetrievalReport]) -> str:
    k = reports[0].k
    lines = [
        "# Avaliação da busca semântica",
        "",
        f"{len(reports[0].results)} consultas com gabarito em `data/eval/retrieval.json`.",
        "",
        f"| Configuração | recall@{k} | MRR |",
        "|---|---|---|",
    ]
    for r in reports:
        lines.append(f"| {r.embedding} | {r.mean_recall:.3f} | {r.mrr:.3f} |")

    lines += ["", f"## recall@{k} por consulta", ""]
    lines.append("| Consulta | " + " | ".join(r.embedding for r in reports) + " |")
    lines.append("|---" * (len(reports) + 1) + "|")
    for i, result in enumerate(reports[0].results):
        scores = " | ".join(f"{r.results[i].recall:.2f}" for r in reports)
        lines.append(f"| {result.id}: {result.query} | {scores} |")

    lines += ["", "## Itens que faltaram no top 5", ""]
    for r in reports:
        lines.append(f"**{r.embedding}**")
        lines.append("")
        misses = [x for x in r.results if x.recall < 1]
        if not misses:
            lines.append("- nenhum")
        for x in misses:
            missing = [i for i in x.relevant if i not in x.retrieved]
            lines.append(f"- {x.id} ({x.query}): faltou {', '.join(missing)}; veio {', '.join(x.retrieved)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    catalog = load_catalog()
    cases = load_cases()
    reports = []
    for label, embedding, enrich in CONFIGS:
        print(f"Avaliando {label}...")
        retriever = Retriever(catalog, embedding=embedding, enrich=enrich)
        report = evaluate(retriever, label, cases, k=args.k)
        print(f"  recall@{args.k} = {report.mean_recall:.3f}   MRR = {report.mrr:.3f}")
        reports.append(report)

    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "retrieval.md").write_text(to_markdown(reports), encoding="utf-8")
    (REPORTS_DIR / "retrieval.json").write_text(
        json.dumps([r.model_dump() for r in reports], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Relatório em {REPORTS_DIR / 'retrieval.md'}")


if __name__ == "__main__":
    main()
