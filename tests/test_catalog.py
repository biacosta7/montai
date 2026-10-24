"""Testes de sanidade do catálogo.

A avaliação inteira usa as tags de dieta do catálogo como gabarito. Se uma
tag estiver errada (um item "vegano" com queijo), as métricas de restrição
mentem. Por isso o catálogo tem testes próprios.
"""

import importlib.util
import re

import pytest

from montai.catalog import load_catalog
from montai.config import CATALOG_PATH, ROOT_DIR
from montai.models import Category, DietTag


def _load_generator():
    path = ROOT_DIR / "scripts" / "generate_catalog.py"
    spec = importlib.util.spec_from_file_location("generate_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def test_json_versionado_bate_com_o_script():
    """O JSON no repositório precisa ser exatamente o que o script gera."""
    generator = _load_generator()
    assert CATALOG_PATH.read_text(encoding="utf-8") == generator.render(generator.build_catalog())


def test_tamanho_do_catalogo(catalog):
    assert 15 <= len(catalog.stores) <= 20
    assert 300 <= len(catalog.items) <= 500


def test_toda_loja_tem_itens_suficientes(catalog):
    for store in catalog.stores:
        count = sum(1 for i in catalog.items if i.store_id == store.id)
        assert count >= 10, store.id


def test_toda_categoria_tem_itens(catalog):
    used = {i.category for i in catalog.items}
    assert used == set(Category)


def test_combinacoes_de_restricao_tem_cobertura(catalog):
    """Pedidos 'vegano + sem glúten' precisam ser possíveis em várias categorias."""
    strict = {DietTag.VEGANO, DietTag.SEM_GLUTEN}
    categories = {i.category for i in catalog.items if i.satisfies(strict)}
    assert len(categories) >= 6


# Palavras que denunciam ingrediente animal ou lácteo. Trechos como
# "sem queijo" ou "leite de coco" são removidos antes da checagem.
MEAT_WORDS = [
    "carne", "frango", "bacon", "linguiça", "calabresa", "presunto", "peru", "salame",
    "pepperoni", "peixe", "salmão", "atum", "camarão", "tilápia", "bacalhau", "porco",
    "picanha", "costela", "kani", "kafta",
]
DAIRY_WORDS = [
    "queijo", "muçarela", "catupiry", "cheddar", "manteiga", "creme de leite", "requeijão",
    "iogurte", "cream cheese", "parmesão", "ricota", "coalhada", "leite", "mascarpone",
    "provolone", "gorgonzola", "pepper jack", "creme azedo",
]
NON_DAIRY = [
    "leite de coco", "bebida vegetal", "bebida de aveia", "bebida de amêndoas",
    "queijo vegetal tipo muçarela", "queijo vegetal", "maionese vegana", "leite de aveia",
    "alternativa ao leite", "couve manteiga",
]


def _text(item) -> str:
    text = f"{item.name} {item.description}".lower()
    for phrase in NON_DAIRY:
        text = text.replace(phrase, "")
    return re.sub(r"\bsem \w+", "", text)


def _contains(text: str, words: list[str]) -> list[str]:
    return [w for w in words if re.search(rf"\b{re.escape(w)}\b", text)]


def test_vegetarianos_nao_tem_carne(catalog):
    bad = [
        (i.id, _contains(_text(i), MEAT_WORDS))
        for i in catalog.items
        if DietTag.VEGETARIANO in i.diet and _contains(_text(i), MEAT_WORDS)
    ]
    assert bad == []


def test_sem_lactose_nao_tem_laticinio(catalog):
    bad = [
        (i.id, _contains(_text(i), DAIRY_WORDS))
        for i in catalog.items
        if DietTag.SEM_LACTOSE in i.diet and _contains(_text(i), DAIRY_WORDS)
    ]
    assert bad == []


def test_get_item_por_id(catalog):
    first = catalog.items[0]
    assert catalog.get_item(first.id) == first
    assert catalog.get_item("nao-existe-999") is None
