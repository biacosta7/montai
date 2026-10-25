"""Interpretador: pedido em texto livre -> OrderSpec estruturada.

É a única etapa que lê o texto do cliente. Daqui em diante, tudo trabalha
sobre campos tipados, e o resto do pipeline não precisa "entender português".
"""

from __future__ import annotations

from montai.llm import LLMClient
from montai.models import Category, DietTag, OrderSpec
from montai.tracing import Step

CATEGORY_GUIDE = {
    Category.GRELHADOS: "carnes, linguiças, espetinhos e opções vegetais para grelhar ou já assados",
    Category.PRATO_PRINCIPAL: "refeições prontas, pratos, combos, pizzas, sushi, kits de café da manhã",
    Category.ACOMPANHAMENTO: "arroz, farofa, vinagrete, pão de alho, batata frita",
    Category.SALADA: "saladas prontas e folhas",
    Category.ENTRADA: "petiscos, salgados, porções, sopas, pastas",
    Category.LANCHE: "sanduíches, hambúrgueres, wraps, tapiocas, tacos",
    Category.PAES: "pães, croissants, pão de queijo",
    Category.FRIOS_LATICINIOS: "queijos, presunto, manteiga, requeijão, geleia",
    Category.HORTIFRUTI: "frutas, verduras e legumes in natura ou cortados",
    Category.SOBREMESA: "doces, bolos, tortas, sorvetes",
    Category.BEBIDA: "bebidas sem álcool: refrigerante, suco, água, café, leite",
    Category.BEBIDA_ALCOOLICA: "cerveja, vinho, destilados",
    Category.UTENSILIOS: "carvão, gelo, descartáveis",
}

SYSTEM_PROMPT = f"""Você é o Interpretador do Montaí, um assistente que monta carrinhos de delivery.
Transforme o pedido do cliente numa especificação estruturada. Não escolha itens nem preços.

Categorias disponíveis (use exatamente estes valores):
{chr(10).join(f"- {c.value}: {desc}" for c, desc in CATEGORY_GUIDE.items())}

Restrições alimentares possíveis: {", ".join(t.value for t in DietTag)}.
Picância: 0 = nada apimentado, 1 = leve, 2 = média, 3 = alta.

Regras:
- specific_dish: o prato ou item que o cliente nomeou ("pizza", "lasanha", "risoto", "hambúrguer").
  Use null para pedidos genéricos ("jantar", "almoço caseiro", "comida árabe", "uma festa").
- people: número de pessoas. Se o pedido não disser, suponha um valor razoável e registre em assumptions.
- budget: orçamento TOTAL em reais (incluindo entrega). null se não houver.
- diet: restrições que valem para TODOS os itens ("sem glúten", "somos veganos").
- diet_options: restrições que valem só para parte do pedido ("uma opção vegana").
- max_spice: 0 se o cliente pedir "nada apimentado"/"sem pimenta"; 1 para "pouco apimentado"; senão null.
- needs: de 1 a 5 categorias que a ocasião realmente pede, cada uma com uma consulta curta em português
  para a busca (ex.: "carnes para churrasco"). Respeite o que o cliente pediu explicitamente e complete
  com o essencial da ocasião (ex.: churrasco pede grelhados, acompanhamento, bebida e carvão).
  Com orçamento apertado, inclua só o essencial.
- essential = true para o que precisa alimentar todas as pessoas (a comida principal e, se pedida, a bebida).
  Itens de apoio (carvão, sobremesa opcional, acompanhamento) ficam essential = false.
- assumptions: liste em português cada suposição feita sobre um pedido vago.
"""

EXAMPLE_ORDER = "pizza para 3, sem lactose, até 150 reais"
EXAMPLE_SPEC = OrderSpec(
    occasion="jantar com pizza",
    specific_dish="pizza",
    people=3,
    budget=150,
    diet=[DietTag.SEM_LACTOSE],
    diet_options=[],
    max_spice=None,
    needs=[
        {"category": Category.PRATO_PRINCIPAL, "query": "pizza", "essential": True},
        {"category": Category.BEBIDA, "query": "refrigerante", "essential": False},
    ],
    assumptions=["Bebida incluída como item de apoio, não foi pedida explicitamente."],
)


def interpret(order: str, llm: LLMClient, step: Step | None = None) -> OrderSpec:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        # Um exemplo resolvido (few-shot) ensina o formato melhor que só regras.
        {"role": "user", "content": EXAMPLE_ORDER},
        {"role": "assistant", "content": EXAMPLE_SPEC.model_dump_json()},
        {"role": "user", "content": order},
    ]
    spec = llm.structured(messages, OrderSpec, step=step)
    return normalize_spec(spec)


def normalize_spec(spec: OrderSpec) -> OrderSpec:
    """Correções determinísticas sobre a saída do modelo."""
    people = max(1, spec.people)
    budget = spec.budget if spec.budget and spec.budget > 0 else None
    diet = list(dict.fromkeys(spec.diet))
    # Uma "opção" que já vale para todos os itens é redundante.
    diet_options = [t for t in dict.fromkeys(spec.diet_options) if t not in diet]
    # Uma categoria por necessidade; se repetir, vale a primeira.
    seen: set[Category] = set()
    needs = []
    for need in spec.needs:
        if need.category not in seen:
            seen.add(need.category)
            needs.append(need)
    return spec.model_copy(update={
        "people": people, "budget": budget, "diet": diet, "diet_options": diet_options, "needs": needs,
    })
