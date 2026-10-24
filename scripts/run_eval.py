"""Roda a avaliação completa e gera o relatório comparativo.

Uso:
    python scripts/run_eval.py --versions B           # roda o que faltar e gera o relatório
    python scripts/run_eval.py --versions B --cases o01,i05 --force
    python scripts/run_eval.py --report-only           # só recalcula o relatório

Pedidos já executados (reports/runs/) são pulados, então dá para interromper
e retomar. Se a cota diária do provedor acabar, o script para e salva o que
já rodou.
"""

from __future__ import annotations

import argparse
import json

from montai.catalog import load_catalog
from montai.config import REPORTS_DIR
from montai.eval.metrics import load_cases, score_case
from montai.eval.report import summarize, to_markdown
from montai.eval.runner import RunRecord, load_records, make_runners, now, save_record
from montai.llm import LLMClient, QuotaExhausted
from montai.retrieval import Retriever

ALL_VERSIONS = ["A", "B"]


def run(versions: list[str], case_ids: set[str] | None, force: bool) -> None:
    catalog = load_catalog()
    cases = [c for c in load_cases() if not case_ids or c.id in case_ids]
    llm = LLMClient()
    runners = make_runners(llm, Retriever(catalog), catalog)

    for version in versions:
        if version not in runners:
            print(f"Versão {version} ainda não implementada; pulando.")
            continue
        done = load_records(version)
        pending = [c for c in cases if force or c.id not in done]
        print(f"Versão {version}: {len(pending)} pedido(s) para rodar.")
        for n, case in enumerate(pending, start=1):
            try:
                output = runners[version](case.order)
            except QuotaExhausted as exc:
                print(f"\nParando: {exc}. Rode de novo mais tarde para continuar.")
                return
            save_record(RunRecord(
                case_id=case.id, version=version, model=llm.model, order=case.order,
                finished_at=now(), cart=output.cart, spec=output.spec, trace=output.trace,
            ))
            score = score_case(case, output.cart, catalog)
            print(f"  [{n}/{len(pending)}] {case.id} {output.cart.status.value:<10} "
                  f"{'ok ' if score.success else 'ERR'} {output.trace.latency_ms / 1000:5.1f}s  {case.order}")


def report() -> None:
    catalog = load_catalog()
    cases = load_cases()
    summaries, scores = [], {}
    for version in ALL_VERSIONS:
        records = load_records(version)
        if not records:
            continue
        summary, version_scores = summarize(version, records, cases, catalog)
        summaries.append(summary)
        scores[version] = version_scores

    if not summaries:
        print("Nenhum resultado em reports/runs/ ainda.")
        return
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "eval.md").write_text(to_markdown(summaries, scores, cases), encoding="utf-8")
    payload = {
        "summaries": [s.model_dump() for s in summaries],
        "scores": {v: [s.model_dump(mode="json") for s in sc] for v, sc in scores.items()},
    }
    (REPORTS_DIR / "eval.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for s in summaries:
        print(f"Versão {s.version}: {s.cases} pedidos, resolvidos {s.rates['success'].fmt()}")
    print(f"Relatório em {REPORTS_DIR / 'eval.md'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions", default=",".join(ALL_VERSIONS))
    parser.add_argument("--cases", help="ids separados por vírgula (padrão: todos)")
    parser.add_argument("--force", action="store_true", help="roda de novo mesmo se já houver resultado")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    if not args.report_only:
        case_ids = set(args.cases.split(",")) if args.cases else None
        run(args.versions.split(","), case_ids, args.force)
    report()


if __name__ == "__main__":
    main()
