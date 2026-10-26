"""Roda a avaliação completa e gera o relatório comparativo.

Uso:
    python scripts/run_eval.py --versions B           # roda o que faltar e gera o relatório
    python scripts/run_eval.py --versions B --cases o01,i05 --force
    python scripts/run_eval.py --sample 4 --wait-quota # amostra de 4 pedidos por grupo, A e B
    python scripts/run_eval.py --report-only           # só recalcula o relatório

As versões são executadas intercaladas, pedido a pedido: se a avaliação
atravessar dias por causa da cota, A e B avançam juntas, nas mesmas condições.

Pedidos já executados (reports/runs/) são pulados, então dá para interromper
e retomar. Se a cota do provedor acabar, o script para e salva o que já
rodou; com --wait-quota, ele espera a cota voltar e continua sozinho.
"""

from __future__ import annotations

import argparse
import json
import time

from montai.catalog import load_catalog
from montai.config import REPORTS_DIR
from montai.eval.metrics import EvalCase, load_cases, score_case, stratified_sample
from montai.eval.report import summarize, to_markdown
from montai.eval.runner import RunRecord, load_records, make_runners, now, save_record
from montai.llm import MAX_WAIT_S, LLMClient, QuotaExhausted
from montai.retrieval import Retriever

ALL_VERSIONS = ["A", "B"]


def select_cases(case_ids: set[str] | None, sample: int | None) -> list[EvalCase]:
    cases = load_cases()
    if sample:
        cases = stratified_sample(cases, per_group=sample)
    return [c for c in cases if not case_ids or c.id in case_ids]


def run(versions: list[str], cases: list[EvalCase], force: bool, wait_quota: bool) -> None:
    catalog = load_catalog()
    # Na avaliação, esperar a cota dentro da chamada (até 1 h por espera) evita
    # recomeçar pedidos do zero e desperdiçar os tokens já gastos neles.
    llm = LLMClient(max_wait_s=3600 if wait_quota else MAX_WAIT_S)
    runners = make_runners(llm, Retriever(catalog), catalog)
    done = {v: load_records(v) for v in versions}
    pending = [(c, v) for c in cases for v in versions if force or c.id not in done[v]]
    print(f"{len(pending)} execução(ões) pendente(s): {len(cases)} pedido(s) x versões {', '.join(versions)}.")

    for n, (case, version) in enumerate(pending, start=1):
        while True:
            try:
                output = runners[version](case.order)
                break
            except QuotaExhausted as exc:
                if not wait_quota:
                    print(f"\nParando: {exc}. Rode de novo mais tarde para continuar.")
                    return
                print(f"  {exc}; esperando...", flush=True)
                time.sleep(exc.wait_s + 5)
        save_record(RunRecord(
            case_id=case.id, version=version, model=llm.model, order=case.order,
            finished_at=now(), cart=output.cart, spec=output.spec, trace=output.trace,
        ))
        score = score_case(case, output.cart, catalog)
        print(f"  [{n}/{len(pending)}] {version} {case.id} {output.cart.status.value:<10} "
              f"{'ok ' if score.success else 'ERR'} {output.trace.tokens_in + output.trace.tokens_out:>6} tok "
              f"{output.trace.latency_ms / 1000:5.1f}s  {case.order}", flush=True)


def report(cases: list[EvalCase], scope: str) -> None:
    catalog = load_catalog()
    summaries, scores = [], {}
    for version in ALL_VERSIONS:
        records = load_records(version)
        if not records:
            continue
        records = {cid: r for cid, r in records.items() if cid in {c.id for c in cases}}
        if not records:
            continue
        summary, version_scores = summarize(version, records, cases, catalog)
        summaries.append(summary)
        scores[version] = version_scores

    if not summaries:
        print("Nenhum resultado em reports/runs/ ainda.")
        return
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "eval.md").write_text(to_markdown(summaries, scores, cases, scope), encoding="utf-8")
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
    parser.add_argument("--wait-quota", action="store_true", help="espera a cota voltar em vez de parar")
    parser.add_argument("--sample", type=int, help="pedidos sorteados por grupo (amostra estratificada)")
    args = parser.parse_args()

    case_ids = set(args.cases.split(",")) if args.cases else None
    cases = select_cases(case_ids, args.sample)
    if not args.report_only:
        run(args.versions.split(","), cases, args.force, args.wait_quota)
    scope = (
        f"Amostra estratificada: {args.sample} pedidos sorteados por grupo (semente 42), {len(cases)} no total."
        if args.sample else f"{len(cases)} pedidos."
    )
    report(cases, scope)


if __name__ == "__main__":
    main()
