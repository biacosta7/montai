"""Testes do conjunto de avaliação e das métricas.

O gabarito também precisa de teste: se um pedido marcado como "impossível
por orçamento" na verdade fosse possível, a métrica puniria o sistema por
acertar.
"""

from collections import Counter

import pytest

from montai.eval.metrics import EvalCase, load_cases, score_case
from montai.models import Cart, CartLine, CartStatus, DietTag


@pytest.fixture(scope="module")
def cases():
    return load_cases()


def lower_bound_cost(case: EvalCase, catalog) -> float:
    """Custo mínimo otimista da comida principal (permite fração de unidade)."""
    e = case.expected
    options = [
        e.people * i.price / i.serves + catalog.get_store(i.store_id).delivery_fee
        for i in catalog.items
        if e.is_main(i)
        and i.satisfies(set(e.diet))
        and (e.max_spice is None or i.spice_level <= e.max_spice)
    ]
    return min(options)


def test_tamanho_e_grupos(cases):
    assert 40 <= len(cases) <= 50
    assert len({c.id for c in cases}) == len(cases)
    groups = Counter(c.group for c in cases)
    assert set(groups) == {"ocasiao", "orcamento_apertado", "restricoes_combinadas", "impossivel", "ambiguo"}
    assert all(n >= 5 for n in groups.values())


def test_impossiveis_por_orcamento_sao_provados(cases, catalog):
    for case in cases:
        if case.expected.reason == "orcamento":
            assert lower_bound_cost(case, catalog) > case.expected.budget, case.id


def test_possiveis_com_orcamento_nao_sao_descartados_pelo_limite(cases, catalog):
    for case in cases:
        e = case.expected
        if e.possible and e.budget is not None:
            assert lower_bound_cost(case, catalog) <= e.budget, case.id


def cart_from(catalog, *pairs, status=CartStatus.OK, people=None):
    lines = []
    for item_id, qty in pairs:
        item = catalog.get_item(item_id)
        store = catalog.get_store(item.store_id)
        lines.append(CartLine(
            item_id=item.id, name=item.name, store_id=store.id, store_name=store.name,
            unit=item.unit, quantity=qty, unit_price=item.price, subtotal=round(item.price * qty, 2),
        ))
    items = round(sum(line.subtotal for line in lines), 2)
    fees = round(sum(catalog.get_store(s).delivery_fee for s in {line.store_id for line in lines}), 2)
    return Cart(status=status, lines=lines, items_total=items, delivery_total=fees,
                total=round(items + fees, 2), people=people)


def case_by_id(cases, case_id):
    return next(c for c in cases if c.id == case_id)


def test_score_carrinho_correto(cases, catalog):
    # Churrasco para 5 até R$ 200: kit econômico + carvão + refrigerante, tudo no mercado.
    cart = cart_from(catalog, ("mercado-032", 1), ("mercado-015", 1), ("mercado-003", 1))
    score = score_case(case_by_id(cases, "o01"), cart, catalog)
    assert score.success and score.budget_ok and score.quantity_ok and score.catalog_ok
    assert score.diet_ok is None  # caso sem restrição: métrica não se aplica


def test_score_pega_restricao_violada(cases, catalog):
    # "sem glúten" + "nada apimentado", mas veio pão de alho apimentado.
    cart = cart_from(catalog, ("acougue-019", 1), ("caseiro-002", 2))
    score = score_case(case_by_id(cases, "o02"), cart, catalog)
    assert score.diet_ok is False
    assert not score.success


def test_score_pega_preco_adulterado(cases, catalog):
    cart = cart_from(catalog, ("mercado-032", 1), ("mercado-015", 1))
    cart.lines[0].unit_price = 1.0
    assert score_case(case_by_id(cases, "o01"), cart, catalog).catalog_ok is False


def test_score_impossivel(cases, catalog):
    case = case_by_id(cases, "i01")
    refused = score_case(case, Cart(status=CartStatus.IMPOSSIBLE), catalog)
    assert refused.success and refused.classification_ok
    delivered = score_case(case, cart_from(catalog, ("mercado-032", 1)), catalog)
    assert not delivered.classification_ok and not delivered.success


def test_score_ambiguo_usa_pessoas_assumidas(cases, catalog):
    case = case_by_id(cases, "a01")
    assert case.expected.people is None
    cart = cart_from(catalog, ("caseiro-002", 2), people=2)
    assert score_case(case, cart, catalog).quantity_ok


def test_tags_do_gabarito_sao_validas(cases):
    for case in cases:
        assert set(case.expected.diet) <= set(DietTag)


def test_amostra_estratificada_e_reproduzivel(cases):
    from montai.eval.metrics import stratified_sample

    sample = stratified_sample(cases, per_group=4)
    assert len(sample) == 20
    assert Counter(c.group for c in sample) == {g: 4 for g in {c.group for c in cases}}
    assert [c.id for c in sample] == [c.id for c in stratified_sample(cases, per_group=4)]
