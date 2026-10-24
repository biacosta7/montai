"""Validador determinístico de carrinhos.

É o juiz do sistema: o LLM propõe, este código decide. Nada aqui chama modelo.
As mesmas regras valem para as versões A e B, e a avaliação reaproveita os
mesmos cálculos. Cada problema tem um código (para métricas) e uma mensagem
em português (para devolver ao Montador ou mostrar ao cliente).
"""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, Field

from montai.models import (
    CartLine,
    Catalog,
    Category,
    Constraints,
    DietTag,
    Item,
    ProposalLine,
)
from montai.quantities import max_reasonable_coverage

MAX_UNITS_PER_LINE = 100

# Itens que não são comida: não contam para cobertura nem para excesso.
NON_FOOD = {Category.UTENSILIOS}
# Um prato principal ou combo já é uma refeição: ele cobre as categorias de
# comida exigidas (grelhados, acompanhamento etc.), mas não bebida ou sobremesa.
MEAL_CATEGORY = Category.PRATO_PRINCIPAL
NOT_COVERED_BY_MEAL = {Category.BEBIDA, Category.BEBIDA_ALCOOLICA, Category.SOBREMESA, *NON_FOOD}


class ProblemCode(StrEnum):
    EMPTY_CART = "carrinho_vazio"
    UNKNOWN_ITEM = "item_inexistente"
    INVALID_QUANTITY = "quantidade_invalida"
    BUDGET_EXCEEDED = "orcamento_estourado"
    DIET_VIOLATION = "restricao_violada"
    SPICE_VIOLATION = "picancia_violada"
    MISSING_DIET_OPTION = "opcao_de_dieta_ausente"
    INSUFFICIENT_QUANTITY = "quantidade_insuficiente"
    EXCESSIVE_QUANTITY = "quantidade_excessiva"


class Problem(BaseModel):
    code: ProblemCode
    message: str


class ValidationReport(BaseModel):
    ok: bool
    problems: list[Problem] = Field(default_factory=list)
    lines: list[CartLine] = Field(default_factory=list)
    items_total: float = 0.0
    delivery_total: float = 0.0
    total: float = 0.0
    coverage: dict[str, float] = Field(default_factory=dict)

    def problem_codes(self) -> set[ProblemCode]:
        return {p.code for p in self.problems}


def _merge_lines(lines: list[ProposalLine]) -> dict[str, int]:
    """Soma quantidades se o mesmo item vier repetido."""
    merged: dict[str, int] = defaultdict(int)
    for line in lines:
        merged[line.item_id] += line.quantity
    return dict(merged)


def category_coverage(items: list[tuple[Item, int]]) -> dict[Category, float]:
    """Quantas pessoas cada categoria atende (unidades x serves)."""
    coverage: dict[Category, float] = defaultdict(float)
    for item, qty in items:
        if item.category not in NON_FOOD:
            coverage[item.category] += item.serves * qty
    return dict(coverage)


def validate_cart(lines: list[ProposalLine], constraints: Constraints, catalog: Catalog) -> ValidationReport:
    problems: list[Problem] = []

    def add(code: ProblemCode, message: str) -> None:
        problems.append(Problem(code=code, message=message))

    # 1. Itens existem no catálogo e quantidades são válidas (regra 1).
    resolved: list[tuple[Item, int]] = []
    for item_id, qty in _merge_lines(lines).items():
        item = catalog.get_item(item_id)
        if item is None:
            add(ProblemCode.UNKNOWN_ITEM, f"O item '{item_id}' não existe no catálogo.")
            continue
        if not 1 <= qty <= MAX_UNITS_PER_LINE:
            add(ProblemCode.INVALID_QUANTITY, f"Quantidade {qty} inválida para '{item.name}'.")
            continue
        resolved.append((item, qty))

    if not resolved:
        add(ProblemCode.EMPTY_CART, "O carrinho está vazio.")
        return ValidationReport(ok=False, problems=problems)

    # 2. Restrições alimentares e picância, item a item (regra 2).
    required_diet = set(constraints.diet)
    for item, _ in resolved:
        if item.category in NON_FOOD:
            continue
        missing = required_diet - set(item.diet)
        if missing:
            tags = ", ".join(sorted(t.value for t in missing))
            add(ProblemCode.DIET_VIOLATION, f"'{item.name}' ({item.id}) não é {tags}.")
        if constraints.max_spice is not None and item.spice_level > constraints.max_spice:
            add(ProblemCode.SPICE_VIOLATION,
                f"'{item.name}' ({item.id}) tem picância {int(item.spice_level)}, "
                f"acima do máximo {int(constraints.max_spice)}.")

    for tag in constraints.diet_options:
        if not any(tag in item.diet for item, _ in resolved if item.category not in NON_FOOD):
            add(ProblemCode.MISSING_DIET_OPTION, f"Falta pelo menos uma opção {tag.value}.")

    # 3. Preço total, sempre recalculado a partir do catálogo.
    cart_lines = []
    for item, qty in resolved:
        store = catalog.get_store(item.store_id)
        cart_lines.append(CartLine(
            item_id=item.id, name=item.name, store_id=store.id, store_name=store.name,
            unit=item.unit, quantity=qty, unit_price=item.price, subtotal=round(item.price * qty, 2),
        ))
    items_total = round(sum(line.subtotal for line in cart_lines), 2)
    store_ids = {line.store_id for line in cart_lines}
    delivery_total = round(sum(catalog.get_store(s).delivery_fee for s in store_ids), 2)
    total = round(items_total + delivery_total, 2)
    if constraints.budget is not None and total > constraints.budget + 0.005:
        add(ProblemCode.BUDGET_EXCEEDED,
            f"Total R$ {total:.2f} (itens R$ {items_total:.2f} + entrega R$ {delivery_total:.2f}) "
            f"passa do orçamento de R$ {constraints.budget:.2f} em R$ {total - constraints.budget:.2f}.")

    # 4. Quantidade adequada ao número de pessoas.
    people = constraints.people
    coverage = category_coverage(resolved)
    meal_coverage = coverage.get(MEAL_CATEGORY, 0.0)
    for category in dict.fromkeys(constraints.required_categories):
        if category in NON_FOOD:
            continue
        covered = coverage.get(category, 0.0)
        if category not in NOT_COVERED_BY_MEAL and category != MEAL_CATEGORY:
            covered += meal_coverage
        if covered + 1e-9 < people:
            add(ProblemCode.INSUFFICIENT_QUANTITY,
                f"'{category.value}' atende {covered:g} pessoa(s), mas o pedido é para {people}.")

    for category, covered in coverage.items():
        largest = max(i.serves for i, _ in resolved if i.category == category)
        limit = max_reasonable_coverage(people, largest)
        if covered > limit + 1e-9:
            add(ProblemCode.EXCESSIVE_QUANTITY,
                f"'{category.value}' atende {covered:g} pessoas para um pedido de {people}: "
                f"é desperdício (limite {limit:g}).")

    return ValidationReport(
        ok=not problems,
        problems=problems,
        lines=cart_lines,
        items_total=items_total,
        delivery_total=delivery_total,
        total=total,
        coverage={c.value: round(v, 2) for c, v in coverage.items()},
    )


def diet_label(tags: list[DietTag]) -> str:
    return ", ".join(t.value for t in tags) if tags else "nenhuma"
