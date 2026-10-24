"""Testes do orquestrador da versão B com um LLM roteirizado."""

import pytest

from montai.llm import strict_json_schema
from montai.models import (
    CartProposal,
    CartStatus,
    Category,
    CategoryNeed,
    DietTag,
    OrderSpec,
    ProposalLine,
)
from montai.pipeline.orchestrator import MAX_REPAIRS, run_pipeline


def churrasco_spec(budget=300.0, people=5, diet=None):
    return OrderSpec(
        occasion="churrasco",
        people=people,
        budget=budget,
        diet=diet or [],
        diet_options=[],
        max_spice=None,
        needs=[
            CategoryNeed(category=Category.GRELHADOS, query="carnes para churrasco", essential=True),
            CategoryNeed(category=Category.UTENSILIOS, query="carvão", essential=False),
        ],
        assumptions=[],
    )


def proposal(*pairs, feasible=True):
    return CartProposal(
        feasible=feasible,
        lines=[ProposalLine(item_id=i, quantity=q) for i, q in pairs],
        rationale="teste",
    )


def steps(result):
    return [s.name for s in result.trace.steps]


def run(llm, retriever, catalog):
    return run_pipeline("pedido de teste", llm=llm, retriever=retriever, catalog=catalog, log=False)


def test_caminho_feliz(fake_llm, retriever, catalog):
    llm = fake_llm([churrasco_spec(), proposal(("acougue-001", 2), ("acougue-021", 1))])
    result = run(llm, retriever, catalog)
    assert result.cart.status == CartStatus.OK
    assert steps(result) == ["interpretador", "buscador", "pre_checagem", "montador", "validador"]
    assert result.cart.total == round(2 * 94.90 + 32.90 + 7.90, 2)
    assert result.trace.tokens_in > 0


def test_validador_devolve_problema_e_montador_corrige(fake_llm, retriever, catalog):
    llm = fake_llm([
        churrasco_spec(budget=150),
        proposal(("acougue-001", 2)),  # 197,70: estoura o orçamento
        proposal(("acougue-003", 2)),  # fraldinha: 107,70
    ])
    result = run(llm, retriever, catalog)
    assert result.cart.status == CartStatus.OK
    assert steps(result).count("montador") == 2
    # O feedback enviado ao Montador cita o problema encontrado em código.
    feedback = llm.calls[-1][1][-1]["content"]
    assert "orçamento" in feedback


def test_desiste_depois_do_limite_de_tentativas(fake_llm, retriever, catalog):
    bad = [proposal(("acougue-001", 2)) for _ in range(MAX_REPAIRS + 1)]
    result = run(fake_llm([churrasco_spec(budget=150), *bad]), retriever, catalog)
    assert result.cart.status == CartStatus.FAILED
    assert result.cart.lines == []  # nunca devolve carrinho inválido
    assert steps(result).count("montador") == MAX_REPAIRS + 1


def test_item_fora_do_catalogo_nunca_passa(fake_llm, retriever, catalog):
    bad = [proposal(("picanha-inventada", 2)) for _ in range(MAX_REPAIRS + 1)]
    result = run(fake_llm([churrasco_spec(), *bad]), retriever, catalog)
    assert result.cart.status == CartStatus.FAILED


def test_orcamento_impossivel_detectado_sem_chamar_montador(fake_llm, retriever, catalog):
    llm = fake_llm([churrasco_spec(budget=20, people=20)])
    result = run(llm, retriever, catalog)
    assert result.cart.status == CartStatus.IMPOSSIBLE
    assert "montador" not in steps(result)
    assert len(llm.calls) == 1


def test_categoria_sem_candidatos_e_impossivel(fake_llm, retriever, catalog):
    # Nenhum item de grelhados vegano custa até R$ 5: o filtro de preço esvazia
    # a busca e a pré-checagem recusa o pedido sem chamar o Montador.
    spec = churrasco_spec(budget=5, people=2, diet=[DietTag.VEGANO])
    result = run(fake_llm([spec]), retriever, catalog)
    assert result.cart.status == CartStatus.IMPOSSIBLE
    assert "Não há itens de 'grelhados'" in result.cart.message


def test_montador_declara_impossivel(fake_llm, retriever, catalog):
    result = run(fake_llm([churrasco_spec(), proposal(feasible=False)]), retriever, catalog)
    assert result.cart.status == CartStatus.IMPOSSIBLE


@pytest.mark.parametrize("schema", [OrderSpec, CartProposal])
def test_schema_estrito(schema):
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                check(v)
        elif isinstance(node, list):
            for v in node:
                check(v)

    check(strict_json_schema(schema))
