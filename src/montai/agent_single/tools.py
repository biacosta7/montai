"""Ferramentas do agente da versão A.

Cada ferramenta tem:
- um modelo Pydantic de argumentos, que gera o JSON Schema enviado ao LLM e
  valida o que o LLM mandou de volta;
- uma implementação em código que devolve um dict serializável.

Erros (id inexistente, argumento inválido) voltam como {"erro": ...} para o
modelo corrigir, em vez de derrubar o loop.

O estado do carrinho fica no Toolbox, não no modelo: o carrinho final é o que
o código montou e validou, nunca um texto escrito pelo LLM.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from montai.llm import provider_json_schema
from montai.models import Catalog, Category, Constraints, DietTag, Item, ProposalLine, SpiceLevel
from montai.quantities import units_needed
from montai.retrieval import Retriever, SearchFilters
from montai.validation import ValidationReport, validate_cart

# --- Argumentos -------------------------------------------------------------


class BuscarItensArgs(BaseModel):
    """Busca semântica no catálogo, com filtros exatos."""

    consulta: str = Field(description="O que procurar, em português. Ex.: 'carnes para churrasco'.")
    categoria: Category | None = Field(default=None, description="Restringe a uma categoria.")
    dieta: list[DietTag] = Field(default_factory=list, description="Todas as tags que o item precisa ter.")
    preco_maximo: float | None = Field(default=None, description="Preço máximo da unidade, em reais.")
    picancia_maxima: SpiceLevel | None = Field(default=None, description="0 a 3.")
    limite: int = Field(default=6, ge=1, le=12)


class DetalhesItemArgs(BaseModel):
    """Detalhes completos de um item do catálogo."""

    item_id: str


class CalcularQuantidadeArgs(BaseModel):
    """Quantas unidades de um item alimentam N pessoas, e quanto custa."""

    item_id: str
    pessoas: int = Field(ge=1)


class LinhaCarrinho(BaseModel):
    item_id: str
    quantidade: int


class MontarCarrinhoArgs(BaseModel):
    """Monta (ou substitui) o carrinho atual. Preços e totais vêm do catálogo."""

    itens: list[LinhaCarrinho]


class ValidarCarrinhoArgs(BaseModel):
    """Confere o carrinho atual contra as restrições do pedido, em código."""

    pessoas: int = Field(ge=1)
    orcamento: float | None = Field(default=None, description="Orçamento total em reais, com entrega.")
    dieta: list[DietTag] = Field(default_factory=list, description="Restrições que valem para todos os itens.")
    opcoes_dieta: list[DietTag] = Field(
        default_factory=list, description="Restrições que valem para pelo menos um item (ex.: 'uma opção vegana')."
    )
    picancia_maxima: SpiceLevel | None = None
    categorias_essenciais: list[Category] = Field(
        default_factory=list, description="Categorias que precisam alimentar todas as pessoas."
    )

    def constraints(self) -> Constraints:
        return Constraints(
            people=self.pessoas,
            budget=self.orcamento,
            diet=self.dieta,
            diet_options=self.opcoes_dieta,
            max_spice=self.picancia_maxima,
            required_categories=self.categorias_essenciais,
        )


TOOL_ARGS: dict[str, type[BaseModel]] = {
    "buscar_itens": BuscarItensArgs,
    "detalhes_item": DetalhesItemArgs,
    "calcular_quantidade": CalcularQuantidadeArgs,
    "montar_carrinho": MontarCarrinhoArgs,
    "validar_carrinho": ValidarCarrinhoArgs,
}


def tool_schemas() -> list[dict]:
    """Definições no formato de function calling da API da OpenAI."""
    schemas = []
    for name, args in TOOL_ARGS.items():
        parameters = provider_json_schema(args)
        parameters.pop("title", None)
        schemas.append({
            "type": "function",
            "function": {"name": name, "description": args.__doc__.strip(), "parameters": parameters},
        })
    return schemas


# --- Implementação ----------------------------------------------------------


class Toolbox:
    def __init__(self, catalog: Catalog, retriever: Retriever) -> None:
        self.catalog = catalog
        self.retriever = retriever
        self.cart_lines: list[ProposalLine] = []
        self.last_constraints: Constraints | None = None
        self.last_report: ValidationReport | None = None
        self.validated_cart_lines: list[ProposalLine] | None = None

    def call(self, name: str, raw_arguments: str) -> dict[str, Any]:
        """Executa uma ferramenta a partir do nome e dos argumentos em JSON."""
        if name not in TOOL_ARGS:
            return {"erro": f"ferramenta desconhecida: {name}"}
        try:
            args = TOOL_ARGS[name].model_validate(json.loads(raw_arguments or "{}"))
        except (json.JSONDecodeError, ValidationError) as exc:
            return {"erro": f"argumentos inválidos: {exc}"}
        return getattr(self, name)(args)

    def _item_summary(self, item: Item) -> dict[str, Any]:
        store = self.catalog.get_store(item.store_id)
        return {
            "id": item.id,
            "nome": item.name,
            "categoria": item.category.value,
            "loja": store.name,
            "preco": item.price,
            "unidade": item.unit,
            "serve_pessoas": item.serves,
            "dieta": [t.value for t in item.diet],
            "picancia": int(item.spice_level),
        }

    def buscar_itens(self, args: BuscarItensArgs) -> dict[str, Any]:
        filters = SearchFilters(
            categories=[args.categoria] if args.categoria else [],
            diet=args.dieta,
            max_price=args.preco_maximo,
            max_spice=args.picancia_maxima,
        )
        hits = self.retriever.search(args.consulta, filters, k=args.limite)
        return {"resultados": [self._item_summary(h.item) for h in hits]}

    def detalhes_item(self, args: DetalhesItemArgs) -> dict[str, Any]:
        item = self.catalog.get_item(args.item_id)
        if item is None:
            return {"erro": f"item '{args.item_id}' não existe no catálogo"}
        store = self.catalog.get_store(item.store_id)
        return {**self._item_summary(item), "descricao": item.description, "taxa_entrega_loja": store.delivery_fee}

    def calcular_quantidade(self, args: CalcularQuantidadeArgs) -> dict[str, Any]:
        item = self.catalog.get_item(args.item_id)
        if item is None:
            return {"erro": f"item '{args.item_id}' não existe no catálogo"}
        units = units_needed(args.pessoas, item.serves)
        return {
            "item_id": item.id,
            "unidades": units,
            "pessoas_atendidas": round(units * item.serves, 2),
            "custo": round(units * item.price, 2),
        }

    def montar_carrinho(self, args: MontarCarrinhoArgs) -> dict[str, Any]:
        unknown = [line.item_id for line in args.itens if self.catalog.get_item(line.item_id) is None]
        if unknown:
            return {"erro": f"itens inexistentes no catálogo: {', '.join(unknown)}"}
        self.cart_lines = [ProposalLine(item_id=line.item_id, quantity=line.quantidade) for line in args.itens]
        self.validated_cart_lines = None  # carrinho mudou: precisa validar de novo
        # Validação "neutra" só para calcular totais; as regras vêm em validar_carrinho.
        report = validate_cart(self.cart_lines, Constraints(people=1), self.catalog)
        return {
            "linhas": [
                {"item_id": line.item_id, "nome": line.name, "loja": line.store_name,
                 "quantidade": line.quantity, "subtotal": line.subtotal}
                for line in report.lines
            ],
            "itens": report.items_total,
            "entrega": report.delivery_total,
            "total": report.total,
        }

    def validar_carrinho(self, args: ValidarCarrinhoArgs) -> dict[str, Any]:
        if not self.cart_lines:
            return {"erro": "nenhum carrinho montado; chame montar_carrinho antes"}
        constraints = args.constraints()
        report = validate_cart(self.cart_lines, constraints, self.catalog)
        self.last_constraints = constraints
        self.last_report = report
        self.validated_cart_lines = list(self.cart_lines) if report.ok else None
        return {
            "ok": report.ok,
            "total": report.total,
            "problemas": [p.message for p in report.problems],
            "pessoas_atendidas_por_categoria": report.coverage,
        }
