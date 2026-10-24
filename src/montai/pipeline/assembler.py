"""Montador: escolhe itens e quantidades a partir dos candidatos.

O modelo vê uma tabela com os candidatos (id, preço, porção e a quantidade
sugerida para o número de pessoas) e responde só com ids e quantidades.
Nomes, preços e totais são recalculados pelo validador a partir do catálogo,
então o modelo não tem como "alucinar" um preço.
"""

from __future__ import annotations

from montai.models import Catalog, OrderSpec
from montai.pipeline.searcher import NeedCandidates
from montai.quantities import units_needed
from montai.validation import ValidationReport, diet_label

SYSTEM_PROMPT = """Você é o Montador do Montaí. Monte um carrinho de delivery usando SOMENTE os itens
das tabelas de candidatos (use o id exato).

Regras:
1. Escolha itens que combinem com a ocasião (sushi não é café da manhã; carvão é de churrasco).
   A busca pode trazer candidatos fora de contexto: ignore-os.
2. Quantidades são números inteiros de unidades (>= 1).
3. Para contar pessoas, use SEMPRE a coluna "serve" (pessoas por unidade), nunca o nome do item:
   "20 peças" ou "1 kg" não dizem quantas pessoas o item serve.
4. Para cada categoria ESSENCIAL, a soma de (quantidade x "serve") precisa ser >= número de pessoas.
   Um item de prato_principal (prato ou combo) já conta como refeição para as categorias de comida.
5. Não exagere: em cada categoria, a soma de (quantidade x "serve") não deve passar do dobro das pessoas,
   a não ser que uma única unidade grande (um bolo, um saco de carvão) já passe disso.
6. Total = soma dos itens + taxa de entrega de CADA loja usada. O total precisa caber no orçamento.
   Usar menos lojas economiza entrega.
7. Monte um pedido completo para a ocasião: inclua as categorias opcionais que couberem no orçamento.
   Não é preciso gastar tudo, mas deixar de fora o básico da ocasião (ex.: carvão num churrasco) é ruim.
   Sem orçamento informado, monte o básico da ocasião pelo menor custo, sem extras.
8. Compare custos pela coluna "R$/pessoa". Entre itens equivalentes, prefira o de menor R$/pessoa.
   Pratos principais, lanches e grelhados são, cada um, uma refeição: não some vários deles para as
   mesmas pessoas.
9. "Opções obrigatórias" (ex.: uma opção vegana) valem para PARTE das pessoas: inclua ao menos um item
   com essa tag e atenda o restante com os itens comuns, que costumam ser mais baratos. Não troque o
   pedido inteiro pela opção.
10. Se nenhum candidato atende ao que o cliente pediu (ex.: pediu pizza e não há pizza compatível),
   responda feasible = false, lines vazio, e explique em rationale.
11. rationale: 1 a 3 frases em português para o cliente, explicando as escolhas.
"""


def format_candidates(spec: OrderSpec, candidates: list[NeedCandidates], catalog: Catalog) -> str:
    people = spec.people
    blocks = []
    stores: dict[str, float] = {}
    for nc in candidates:
        kind = "ESSENCIAL" if nc.need.essential else "opcional"
        header = f"## {nc.need.category.value} ({kind}) - busca: \"{nc.need.query}\""
        if not nc.items:
            blocks.append(f"{header}\nNenhum candidato compatível com as restrições.")
            continue
        rows = [
            header,
            (
                f"id | item | loja | preço unit. | unidade | serve | R$/pessoa | qtd p/ {people} pessoas | "
                "custo dessa qtd | dieta | picância"
            ),
        ]
        for item in nc.items:
            store = catalog.get_store(item.store_id)
            stores[store.name] = store.delivery_fee
            qty = units_needed(people, item.serves)
            rows.append(
                f"{item.id} | {item.name} | {store.name} | R$ {item.price:.2f} | {item.unit} | "
                f"{item.serves:g} | R$ {item.price / item.serves:.2f} | {qty} | R$ {qty * item.price:.2f} | "
                f"{diet_label(item.diet)} | "
                f"{int(item.spice_level)}"
            )
        blocks.append("\n".join(rows))

    fees = "\n".join(f"- {name}: R$ {fee:.2f}" for name, fee in sorted(stores.items()))
    budget = f"R$ {spec.budget:.2f}" if spec.budget is not None else "não informado (seja econômico)"
    options = diet_label(spec.diet_options) if spec.diet_options else "nenhuma"
    return (
        f"Pedido: {spec.occasion}\n"
        f"Pessoas: {people}\n"
        f"Orçamento total: {budget}\n"
        f"Restrições para todos os itens: {diet_label(spec.diet)}\n"
        f"Opções obrigatórias (ao menos um item): {options}\n\n"
        + "\n\n".join(blocks)
        + f"\n\nTaxa de entrega por loja:\n{fees}"
    )


def initial_messages(spec: OrderSpec, candidates: list[NeedCandidates], catalog: Catalog) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": format_candidates(spec, candidates, catalog)},
    ]


def feedback_message(report: ValidationReport, budget: float | None) -> str:
    """Mensagem que devolve os problemas do validador ao Montador."""
    problems = "\n".join(f"- {p.message}" for p in report.problems)
    budget_line = f" (orçamento R$ {budget:.2f})" if budget is not None else ""
    return (
        "O validador recusou o carrinho:\n"
        f"{problems}\n\n"
        f"Total calculado: R$ {report.total:.2f}{budget_line}. "
        f"Pessoas atendidas por categoria: {report.coverage}.\n"
        "Corrija e devolva o carrinho completo. Se for impossível atender, use feasible = false."
    )
