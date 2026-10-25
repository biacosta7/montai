"""Métricas automáticas por pedido.

Cada métrica olha o carrinho final e o GABARITO do pedido (não a interpretação
do sistema). Se o sistema entendeu "sem glúten" errado, quem pega é a métrica.

Métricas (None quando não se aplicam ao caso):
- classification_ok: entregou carrinho se e só se o pedido é possível.
- budget_ok: total recalculado pelo catálogo cabe no orçamento do gabarito.
- diet_ok: restrições, opções de dieta e picância do gabarito respeitadas.
- quantity_ok: comida principal alimenta todas as pessoas, sem desperdício.
- catalog_ok: todo id existe e nome/preço batem com o catálogo.
- success: o pedido foi resolvido por completo (todas as anteriores).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from pydantic import BaseModel, Field

from montai.config import EVAL_DIR
from montai.models import (
    Cart,
    CartStatus,
    Catalog,
    Category,
    Constraints,
    DietTag,
    ProposalLine,
    SpiceLevel,
)
from montai.validation import MAIN_COURSES, ProblemCode, validate_cart

ORDERS_PATH = EVAL_DIR / "orders.json"
DEFAULT_MAIN = sorted(MAIN_COURSES)


class Expected(BaseModel):
    possible: bool
    reason: str | None = None  # para impossíveis: "orcamento" ou "restricao"
    people: int | None = None
    budget: float | None = None
    diet: list[DietTag] = Field(default_factory=list)
    diet_options: list[DietTag] = Field(default_factory=list)
    max_spice: SpiceLevel | None = None
    main_categories: list[Category] = Field(default_factory=lambda: list(DEFAULT_MAIN))
    # Quando o pedido nomeia um tipo de comida ("sushi"), só itens dessas lojas
    # contam como comida principal.
    main_stores: list[str] = Field(default_factory=list)

    def is_main(self, item) -> bool:
        return item.category in self.main_categories and (
            not self.main_stores or item.store_id in self.main_stores
        )

    @property
    def has_restrictions(self) -> bool:
        return bool(self.diet or self.diet_options or self.max_spice is not None)


class EvalCase(BaseModel):
    id: str
    group: str
    order: str
    expected: Expected


class CaseScore(BaseModel):
    case_id: str
    group: str
    status: CartStatus
    classification_ok: bool
    budget_ok: bool | None = None
    diet_ok: bool | None = None
    quantity_ok: bool | None = None
    catalog_ok: bool | None = None
    success: bool
    notes: list[str] = Field(default_factory=list)


METRICS = ["classification_ok", "budget_ok", "diet_ok", "quantity_ok", "catalog_ok", "success"]


def load_cases(path: Path = ORDERS_PATH) -> list[EvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [EvalCase.model_validate(c) for c in data["cases"]]


def stratified_sample(cases: list[EvalCase], per_group: int, seed: int = 42) -> list[EvalCase]:
    """Sorteia `per_group` pedidos de cada grupo, com semente fixa.

    O sorteio (e não uma escolha manual) evita escolher sem querer os casos em
    que uma das versões vai melhor. A semente fixa torna a amostra reproduzível.
    """
    rng = random.Random(seed)
    sample = []
    for group in dict.fromkeys(c.group for c in cases):
        members = [c for c in cases if c.group == group]
        sample += sorted(rng.sample(members, min(per_group, len(members))), key=lambda c: c.id)
    return sample


def score_case(case: EvalCase, cart: Cart, catalog: Catalog) -> CaseScore:
    expected = case.expected
    delivered = cart.status == CartStatus.OK
    score = CaseScore(
        case_id=case.id,
        group=case.group,
        status=cart.status,
        classification_ok=delivered == expected.possible,
        success=False,
    )
    if not delivered:
        score.success = not expected.possible
        return score

    # Todas as checagens recalculam a partir dos ids e quantidades, sem
    # confiar em nomes, preços ou totais que vieram no carrinho.
    lines = [ProposalLine(item_id=line.item_id, quantity=line.quantity) for line in cart.lines]
    people = expected.people or cart.people or 1
    report = validate_cart(
        lines,
        Constraints(
            people=people,
            budget=expected.budget,
            diet=expected.diet,
            diet_options=expected.diet_options,
            max_spice=expected.max_spice,
        ),
        catalog,
    )
    codes = report.problem_codes()

    # Catálogo: ids existem e nome/preço/total do carrinho batem com o catálogo.
    catalog_ok = ProblemCode.UNKNOWN_ITEM not in codes and bool(cart.lines)
    for line in cart.lines:
        item = catalog.get_item(line.item_id)
        if item is None or item.name != line.name or abs(item.price - line.unit_price) > 0.005:
            catalog_ok = False
            score.notes.append(f"linha divergente do catálogo: {line.item_id}")
    if abs(report.total - cart.total) > 0.01:
        catalog_ok = False
        score.notes.append(f"total informado {cart.total:.2f} != recalculado {report.total:.2f}")
    score.catalog_ok = catalog_ok

    if expected.budget is not None:
        score.budget_ok = ProblemCode.BUDGET_EXCEEDED not in codes

    if expected.has_restrictions:
        diet_codes = {ProblemCode.DIET_VIOLATION, ProblemCode.SPICE_VIOLATION, ProblemCode.MISSING_DIET_OPTION}
        score.diet_ok = not (codes & diet_codes)

    main_coverage = sum(
        catalog.get_item(line.item_id).serves * line.quantity
        for line in lines
        if catalog.get_item(line.item_id) and expected.is_main(catalog.get_item(line.item_id))
    )
    enough = main_coverage + 1e-9 >= people
    no_waste = ProblemCode.EXCESSIVE_QUANTITY not in codes
    score.quantity_ok = enough and no_waste
    if not enough:
        score.notes.append(f"comida principal atende {main_coverage:g} de {people} pessoas")

    for problem in report.problems:
        if problem.code != ProblemCode.INSUFFICIENT_QUANTITY:
            score.notes.append(problem.message)

    checks = [score.budget_ok, score.diet_ok, score.quantity_ok, score.catalog_ok]
    score.success = expected.possible and all(c is not False for c in checks)
    return score
