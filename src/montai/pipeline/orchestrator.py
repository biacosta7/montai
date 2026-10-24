"""Orquestrador da versão B.

Fluxo:
    Interpretador (LLM) -> Buscador (código) -> Pré-checagem (código)
        -> Montador (LLM) -> Validador (código)
             ^________ problemas (até MAX_REPAIRS vezes) ______|

A pré-checagem detecta pedidos impossíveis sem gastar chamadas ao Montador:
uma categoria essencial sem nenhum candidato, ou um orçamento menor que o
mínimo teórico.
"""

from __future__ import annotations

import openai
from pydantic import BaseModel

from montai.catalog import load_catalog
from montai.llm import LLMClient, LLMError
from montai.models import Cart, CartProposal, CartStatus, Catalog, OrderSpec
from montai.pipeline.assembler import feedback_message, initial_messages
from montai.pipeline.interpreter import interpret
from montai.pipeline.searcher import NeedCandidates, search_candidates
from montai.retrieval import Retriever
from montai.tracing import Trace
from montai.validation import MEAL_CATEGORY, NOT_COVERED_BY_MEAL, diet_label, validate_cart

MAX_REPAIRS = 2  # tentativas de correção depois da primeira montagem


class PipelineResult(BaseModel):
    cart: Cart
    spec: OrderSpec | None = None
    trace: Trace


def check_feasibility(spec: OrderSpec, candidates: list[NeedCandidates], catalog: Catalog) -> list[str]:
    """Prova, sem LLM, que um pedido é impossível. Lista vazia = pode ser possível."""
    meal_items = [i for nc in candidates if nc.need.category == MEAL_CATEGORY for i in nc.items]

    def coverable_by_meal(nc: NeedCandidates) -> bool:
        return nc.need.category not in NOT_COVERED_BY_MEAL and bool(meal_items)

    reasons = []
    for nc in candidates:
        if nc.need.essential and not nc.items and not coverable_by_meal(nc):
            restrictions = diet_label(spec.diet)
            if spec.max_spice is not None:
                restrictions += f", picância até {int(spec.max_spice)}"
            reasons.append(
                f"Não há itens de '{nc.need.category.value}' ('{nc.need.query}') "
                f"compatíveis com as restrições ({restrictions}) e o orçamento."
            )
    if reasons or spec.budget is None:
        return reasons

    # Limite inferior de custo: para cada categoria essencial, o menor preço por
    # pessoa vezes o número de pessoas, mais a entrega mais barata. É uma
    # estimativa otimista (permite "meia unidade"), então se nem ela cabe no
    # orçamento, nenhum carrinho real cabe.
    for nc in candidates:
        if not nc.need.essential or not nc.items:
            continue
        options = nc.items + (meal_items if coverable_by_meal(nc) else [])
        cheapest = min(
            spec.people * i.price / i.serves + catalog.get_store(i.store_id).delivery_fee for i in options
        )
        if cheapest > spec.budget + 0.005:
            reasons.append(
                f"Só '{nc.need.category.value}' para {spec.people} pessoa(s) custa no mínimo "
                f"R$ {cheapest:.2f} com entrega, acima do orçamento de R$ {spec.budget:.2f}."
            )
    return reasons


def run_pipeline(
    order: str,
    *,
    llm: LLMClient,
    retriever: Retriever,
    catalog: Catalog | None = None,
    log: bool = True,
) -> PipelineResult:
    catalog = catalog or load_catalog()
    trace = Trace(version="B", order=order)
    spec: OrderSpec | None = None
    try:
        with trace.step("interpretador", input=order) as step:
            spec = interpret(order, llm, step)
            step.output = spec.model_dump(mode="json")

        with trace.step("buscador", input=[n.model_dump(mode="json") for n in spec.needs]) as step:
            candidates = search_candidates(spec, retriever)
            step.output = {
                nc.need.category.value: [{"id": i.id, "nome": i.name, "score": nc.scores[i.id]} for i in nc.items]
                for nc in candidates
            }

        with trace.step("pre_checagem") as step:
            reasons = check_feasibility(spec, candidates, catalog)
            step.output = {"impossivel": bool(reasons), "motivos": reasons}

        if reasons:
            cart = Cart(
                status=CartStatus.IMPOSSIBLE,
                people=spec.people, budget=spec.budget, assumptions=spec.assumptions,
                message="Não é possível atender este pedido: " + " ".join(reasons),
                problems=reasons,
            )
        else:
            cart = _assemble_with_repairs(spec, candidates, catalog, llm, trace)

    except (LLMError, openai.APIError) as exc:
        cart = Cart(
            status=CartStatus.FAILED,
            message=f"Erro ao consultar o modelo: {exc}",
            people=spec.people if spec else None,
            budget=spec.budget if spec else None,
        )
    finally:
        if log:
            trace.write_jsonl()

    return PipelineResult(cart=cart, spec=spec, trace=trace)


def _assemble_with_repairs(
    spec: OrderSpec, candidates: list[NeedCandidates], catalog: Catalog, llm: LLMClient, trace: Trace
) -> Cart:
    constraints = spec.constraints()
    messages = initial_messages(spec, candidates, catalog)
    base = {"people": spec.people, "budget": spec.budget, "assumptions": spec.assumptions}

    report = None
    for attempt in range(1, MAX_REPAIRS + 2):
        with trace.step("montador", input={"tentativa": attempt}) as step:
            proposal = llm.structured(messages, CartProposal, step=step)
            step.output = proposal.model_dump(mode="json")

        if not proposal.feasible:
            return Cart(status=CartStatus.IMPOSSIBLE, message=proposal.rationale, **base)

        with trace.step("validador", input=[line.model_dump() for line in proposal.lines]) as step:
            report = validate_cart(proposal.lines, constraints, catalog)
            step.output = {
                "ok": report.ok,
                "total": report.total,
                "problemas": [p.model_dump(mode="json") for p in report.problems],
                "cobertura": report.coverage,
            }

        if report.ok:
            return Cart(
                status=CartStatus.OK,
                lines=report.lines,
                items_total=report.items_total,
                delivery_total=report.delivery_total,
                total=report.total,
                message=proposal.rationale,
                **base,
            )

        messages += [
            {"role": "assistant", "content": proposal.model_dump_json()},
            {"role": "user", "content": feedback_message(report, spec.budget)},
        ]

    # Esgotou as tentativas: nunca devolvemos um carrinho inválido como "ok".
    return Cart(
        status=CartStatus.FAILED,
        message="Não consegui montar um carrinho que respeite todas as regras.",
        problems=[p.message for p in report.problems],
        **base,
    )
