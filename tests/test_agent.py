"""Testes da versão A: ferramentas e loop do agente com um LLM roteirizado."""

import json
from types import SimpleNamespace

import pytest

from montai.agent_single.agent import MAX_TURNS, run_agent
from montai.agent_single.tools import Toolbox, tool_schemas
from montai.models import CartStatus

CONSTRAINTS = {"pessoas": 5, "orcamento": 250, "categorias_essenciais": ["grelhados"]}
CART = {"itens": [{"item_id": "acougue-001", "quantidade": 2}, {"item_id": "acougue-021", "quantidade": 1}]}


def call(name, args, call_id="c1"):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def tool_turn(*calls):
    return SimpleNamespace(content="", tool_calls=list(calls))


def text_turn(text):
    return SimpleNamespace(content=text, tool_calls=None)


class ScriptedAgentLLM:
    model = "fake"

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen = []

    def chat(self, messages, *, step=None, tools=None, response_format=None):
        self.seen.append(list(messages))
        if step is not None:
            step.add_usage(100, 20, 0.0)
        return self.turns.pop(0) if self.turns else tool_turn(call("buscar_itens", {"consulta": "x"}))


def run(llm, retriever, catalog):
    return run_agent("pedido de teste", llm=llm, retriever=retriever, catalog=catalog, log=False)


def test_schemas_das_ferramentas():
    names = {t["function"]["name"] for t in tool_schemas()}
    assert names == {"buscar_itens", "detalhes_item", "calcular_quantidade", "montar_carrinho", "validar_carrinho"}
    for tool in tool_schemas():
        assert tool["function"]["description"]
        assert tool["function"]["parameters"]["type"] == "object"


def test_ferramentas_devolvem_erro_em_vez_de_quebrar(retriever, catalog):
    box = Toolbox(catalog, retriever)
    assert "erro" in box.call("detalhes_item", '{"item_id": "nao-existe"}')
    assert "erro" in box.call("calcular_quantidade", '{"item_id": "acougue-001", "pessoas": 0}')
    assert "erro" in box.call("montar_carrinho", '{"itens": [{"item_id": "inventado", "quantidade": 1}]}')
    assert "erro" in box.call("validar_carrinho", '{"pessoas": 2}')  # sem carrinho montado
    assert "erro" in box.call("ferramenta_inventada", "{}")
    assert "erro" in box.call("buscar_itens", "isto não é json")


def test_busca_respeita_filtros(retriever, catalog):
    box = Toolbox(catalog, retriever)
    result = box.call("buscar_itens", json.dumps({"consulta": "jantar", "dieta": ["vegano", "sem_gluten"]}))
    assert result["itens"]
    for row in result["itens"]:
        diet = row.split(" | ")[7]
        assert {"vegano", "sem_gluten"} <= set(diet.split(","))


def test_busca_com_pessoas_traz_quantidade_e_custo(retriever, catalog):
    box = Toolbox(catalog, retriever)
    result = box.call("buscar_itens", json.dumps({"consulta": "picanha", "categoria": "grelhados", "pessoas": 5}))
    assert "unidades p/ 5 pessoas" in result["colunas"]
    row = next(r for r in result["itens"] if r.startswith("acougue-001 "))
    assert row.endswith("| 2 | 189.80")


def test_calcular_quantidade(retriever, catalog):
    result = Toolbox(catalog, retriever).call("calcular_quantidade", '{"item_id": "acougue-001", "pessoas": 5}')
    assert result == {"item_id": "acougue-001", "unidades": 2, "pessoas_atendidas": 5.0, "custo": 189.8}


def test_caminho_feliz(retriever, catalog):
    llm = ScriptedAgentLLM([
        tool_turn(call("montar_carrinho", CART)),
        tool_turn(call("validar_carrinho", CONSTRAINTS)),
        text_turn("Pronto: picanha e carvão para 5."),
    ])
    result = run(llm, retriever, catalog)
    assert result.cart.status == CartStatus.OK
    assert result.cart.total == round(2 * 94.90 + 32.90 + 7.90, 2)
    assert [s.name for s in result.trace.steps] == [
        "agente", "ferramenta:montar_carrinho", "agente", "ferramenta:validar_carrinho", "agente",
    ]
    # O resultado da ferramenta volta ao modelo como mensagem "tool".
    assert llm.seen[1][-1]["role"] == "tool"


def test_carrinho_alterado_depois_de_validar_nao_vale(retriever, catalog):
    llm = ScriptedAgentLLM([
        tool_turn(call("montar_carrinho", CART)),
        tool_turn(call("validar_carrinho", CONSTRAINTS)),
        tool_turn(call("montar_carrinho", {"itens": [{"item_id": "acougue-001", "quantidade": 9}]})),
        text_turn("Pronto!"),
    ])
    assert run(llm, retriever, catalog).cart.status == CartStatus.FAILED


def test_carrinho_reprovado_nao_vale(retriever, catalog):
    llm = ScriptedAgentLLM([
        tool_turn(call("montar_carrinho", CART)),
        tool_turn(call("validar_carrinho", {**CONSTRAINTS, "orcamento": 50})),
        text_turn("Pronto!"),
    ])
    result = run(llm, retriever, catalog)
    assert result.cart.status == CartStatus.FAILED
    assert result.cart.lines == []
    assert any("orçamento" in p for p in result.cart.problems)


def test_agente_declara_impossivel(retriever, catalog):
    llm = ScriptedAgentLLM([text_turn("IMPOSSÍVEL: R$ 10 não alimenta 20 pessoas.")])
    result = run(llm, retriever, catalog)
    assert result.cart.status == CartStatus.IMPOSSIBLE
    assert result.cart.message == "R$ 10 não alimenta 20 pessoas."


def test_limite_de_turnos(retriever, catalog):
    result = run(ScriptedAgentLLM([]), retriever, catalog)
    assert result.cart.status == CartStatus.FAILED
    assert sum(1 for s in result.trace.steps if s.name == "agente") == MAX_TURNS


@pytest.mark.parametrize("ending", ["Pronto!", "IMPOSSÍVEL: não deu"])
def test_validacao_aprovada_vence_texto(retriever, catalog, ending):
    """Se o validador aprovou o carrinho atual, ele vale, mesmo que o texto final diga outra coisa."""
    llm = ScriptedAgentLLM([
        tool_turn(call("montar_carrinho", CART)),
        tool_turn(call("validar_carrinho", CONSTRAINTS)),
        text_turn(ending),
    ])
    assert run(llm, retriever, catalog).cart.status == CartStatus.OK
