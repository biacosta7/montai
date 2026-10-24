"""Testes da busca.

Os filtros são regra dura: nenhum resultado pode violar dieta, preço,
picância ou categoria pedidos. Isso é testado contra o índice real.
"""

import pytest

from montai.eval.retrieval import recall_at_k, reciprocal_rank
from montai.models import Category, DietTag, SpiceLevel
from montai.retrieval import Retriever, SearchFilters, build_where


def test_build_where_sem_filtros():
    assert build_where(None) is None
    assert build_where(SearchFilters()) is None


def test_build_where_uma_condicao_nao_usa_and():
    assert build_where(SearchFilters(diet=[DietTag.VEGANO])) == {"vegano": True}


def test_build_where_varias_condicoes():
    where = build_where(SearchFilters(
        categories=[Category.BEBIDA], diet=[DietTag.SEM_GLUTEN], max_price=10, max_spice=SpiceLevel.LEVE,
    ))
    assert where == {"$and": [
        {"category": {"$in": ["bebida"]}},
        {"sem_gluten": True},
        {"price": {"$lte": 10}},
        {"spice_level": {"$lte": 1}},
    ]}


def test_recall_normalizado_por_k():
    relevant = ["a", "b", "c", "d", "e", "f", "g"]
    assert recall_at_k(["a", "b", "c", "d", "e"], relevant, k=5) == 1.0
    assert recall_at_k(["a", "x", "y", "z", "w"], ["a", "b"], k=5) == 0.5


def test_reciprocal_rank():
    assert reciprocal_rank(["x", "a"], ["a"]) == 0.5
    assert reciprocal_rank(["x", "y"], ["a"]) == 0.0


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    return Retriever(index_dir=tmp_path_factory.mktemp("index"))


def test_busca_encontra_item_obvio(retriever):
    hits = retriever.search("picanha para churrasco", k=5)
    assert "acougue-001" in [h.item.id for h in hits]


def test_filtros_sao_respeitados(retriever):
    filters = SearchFilters(
        categories=[Category.PRATO_PRINCIPAL, Category.LANCHE],
        diet=[DietTag.VEGANO, DietTag.SEM_GLUTEN],
        max_price=45,
        max_spice=SpiceLevel.LEVE,
    )
    hits = retriever.search("jantar", filters, k=10)
    assert hits
    for hit in hits:
        item = hit.item
        assert item.category in filters.categories
        assert item.satisfies(set(filters.diet))
        assert item.price <= 45
        assert item.spice_level <= SpiceLevel.LEVE


def test_filtro_impossivel_retorna_vazio(retriever):
    filters = SearchFilters(categories=[Category.GRELHADOS], diet=[DietTag.VEGANO], max_price=1)
    assert retriever.search("carne", filters) == []


def test_resultados_ordenados_por_similaridade(retriever):
    scores = [h.score for h in retriever.search("sobremesa de chocolate", k=8)]
    assert scores == sorted(scores, reverse=True)
