"""Loop do agente da versão A.

    pedido -> LLM -> chamou ferramenta? -> executa em código -> resultado volta ao LLM -> ...
                  -> respondeu texto?   -> fim

O modelo escolhe as ferramentas, mas o resultado final é decidido em código:
só existe carrinho "ok" se a ferramenta validar_carrinho aprovou exatamente
o carrinho atual. Nenhum texto do modelo vira item, preço ou total.
"""

from __future__ import annotations

import json

import openai
from pydantic import BaseModel

from montai.agent_single.tools import Toolbox, tool_schemas
from montai.catalog import load_catalog
from montai.llm import LLMClient, LLMError
from montai.models import Cart, CartStatus, Catalog
from montai.retrieval import Retriever
from montai.tracing import Trace

MAX_TURNS = 12  # chamadas ao modelo por pedido, para o loop nunca rodar para sempre
IMPOSSIBLE_PREFIX = "IMPOSSÍVEL:"

SYSTEM_PROMPT = f"""Você é o Montaí, um assistente que transforma pedidos vagos em carrinhos de delivery.
Use as ferramentas para buscar itens no catálogo, calcular quantidades, montar e validar o carrinho.

Como trabalhar:
1. Entenda o pedido: número de pessoas (suponha um valor razoável se não for dito), orçamento TOTAL
   (inclui a taxa de entrega de cada loja usada), restrições que valem para todos os itens, opções
   que valem para parte das pessoas ("uma opção vegana"), picância máxima ("nada apimentado" = 0)
   e se o cliente nomeou um prato específico.
2. Busque itens com buscar_itens, por categoria, passando as restrições como filtros e o número
   de pessoas (a busca já devolve unidades e custo para elas). Faça as buscas independentes no
   MESMO turno (ex.: carnes, bebidas e carvão de uma vez): cada turno a mais custa caro.
3. Use a coluna serve (pessoas por unidade) para quantidades, nunca o nome do item:
   "20 peças" ou "1 kg" não dizem quantas pessoas o item serve.
4. Monte com montar_carrinho e confira com validar_carrinho, informando as restrições do pedido
   e as categorias essenciais (as que precisam alimentar todas as pessoas). Se houver problemas,
   corrija e valide de novo.
5. Quando validar_carrinho responder ok, termine com 1 a 3 frases para o cliente explicando o carrinho.

Regras de um bom carrinho:
- Itens combinam com a ocasião (lasanha não é café da manhã; carvão é de churrasco).
- Cada categoria essencial alimenta todas as pessoas. Um prato principal ou combo já é uma refeição.
- Sem exagero: não passe do dobro das pessoas por categoria, salvo uma unidade grande indivisível.
  Pratos principais, lanches e grelhados são, cada um, uma refeição: não some vários para as mesmas pessoas.
- Inclua o básico da ocasião quando couber no orçamento (ex.: carvão num churrasco). Sem orçamento,
  monte o básico pelo menor custo, sem extras. Usar menos lojas economiza entrega.
- "Opções" (ex.: uma opção vegana) valem para PARTE das pessoas: inclua ao menos um item assim e
  atenda o restante com itens comuns.
- Se o cliente nomeou um prato, o item principal TEM que ser esse prato. Não substitua por outro
  (ex.: pediu risoto e não há risoto: não mande lasanha).

Se o pedido for impossível (orçamento insuficiente, ou o prato pedido não existe com as restrições),
não monte carrinho: responda começando com "{IMPOSSIBLE_PREFIX}" e explique o motivo ao cliente.
"""


class AgentResult(BaseModel):
    cart: Cart
    trace: Trace


def _assistant_message(message) -> dict:
    """Converte a mensagem do SDK no formato que volta para o histórico."""
    entry: dict = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        entry["tool_calls"] = [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in message.tool_calls
        ]
    return entry


def _parse_args(raw: str):
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return raw


def run_agent(
    order: str,
    *,
    llm: LLMClient,
    retriever: Retriever,
    catalog: Catalog | None = None,
    log: bool = True,
) -> AgentResult:
    catalog = catalog or load_catalog()
    trace = Trace(version="A", order=order)
    toolbox = Toolbox(catalog, retriever)
    tools = tool_schemas()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": order},
    ]
    final_text: str | None = None

    try:
        for turn in range(1, MAX_TURNS + 1):
            with trace.step("agente", input={"turno": turn}) as step:
                try:
                    message = llm.chat(messages, step=step, tools=tools)
                except openai.BadRequestError as exc:
                    # O Groq recusa chamadas de ferramenta malformadas com
                    # "tool_use_failed". O erro volta ao modelo como mensagem.
                    body = exc.body if isinstance(exc.body, dict) else {}
                    if body.get("code") != "tool_use_failed":
                        raise
                    step.retries += 1
                    step.output = {"erro": body.get("message", str(exc))}
                    messages.append({
                        "role": "user",
                        "content": f"Sua chamada de ferramenta veio malformada: {body.get('message')}. Tente de novo.",
                    })
                    continue
                step.output = {
                    "texto": message.content,
                    "chamadas": [
                        {"ferramenta": tc.function.name, "argumentos": _parse_args(tc.function.arguments)}
                        for tc in message.tool_calls or []
                    ],
                }

            messages.append(_assistant_message(message))
            if not message.tool_calls:
                final_text = (message.content or "").strip()
                break

            for tool_call in message.tool_calls:
                name = tool_call.function.name
                with trace.step(f"ferramenta:{name}", input=_parse_args(tool_call.function.arguments)) as step:
                    result = toolbox.call(name, tool_call.function.arguments)
                    step.output = result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                })

        cart = _final_cart(toolbox, final_text)
    except (LLMError, openai.APIError) as exc:
        cart = Cart(status=CartStatus.FAILED, message=f"Erro ao consultar o modelo: {exc}")
    finally:
        if log:
            trace.write_jsonl()

    return AgentResult(cart=cart, trace=trace)


def _final_cart(toolbox: Toolbox, final_text: str | None) -> Cart:
    constraints = toolbox.last_constraints
    base = {
        "people": constraints.people if constraints else None,
        "budget": constraints.budget if constraints else None,
    }
    if final_text is None:
        return Cart(status=CartStatus.FAILED, message="O agente não terminou dentro do limite de passos.", **base)

    # Só vale o carrinho que o validador aprovou, e só se ele não mudou depois.
    if toolbox.validated_cart_lines is not None and toolbox.validated_cart_lines == toolbox.cart_lines:
        report = toolbox.last_report
        return Cart(
            status=CartStatus.OK,
            lines=report.lines,
            items_total=report.items_total,
            delivery_total=report.delivery_total,
            total=report.total,
            message=final_text,
            **base,
        )

    if final_text.upper().startswith(IMPOSSIBLE_PREFIX.upper()):
        message = final_text[len(IMPOSSIBLE_PREFIX):].strip()
        return Cart(status=CartStatus.IMPOSSIBLE, message=message, **base)

    problems = [p.message for p in toolbox.last_report.problems] if toolbox.last_report else []
    return Cart(
        status=CartStatus.FAILED,
        message="O agente terminou sem um carrinho aprovado pelo validador.",
        problems=problems,
        **base,
    )
