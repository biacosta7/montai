"""Modelos de dados do Montaí.

Todo dado que cruza uma fronteira (arquivo JSON, resposta do LLM, interface)
passa por um modelo Pydantic. Um dado inválido falha cedo, com mensagem clara,
em vez de virar um bug silencioso três etapas depois.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class DietTag(StrEnum):
    VEGANO = "vegano"
    VEGETARIANO = "vegetariano"
    SEM_GLUTEN = "sem_gluten"
    SEM_LACTOSE = "sem_lactose"


class Category(StrEnum):
    """Taxonomia fixa de categorias.

    É uma lista fechada de propósito: o Interpretador (versão B) precisa
    escolher categorias que existem, e o filtro da busca precisa casar com elas.
    """

    GRELHADOS = "grelhados"  # carnes, linguiças, espetinhos e opções vegetais para a grelha
    PRATO_PRINCIPAL = "prato_principal"
    ACOMPANHAMENTO = "acompanhamento"
    SALADA = "salada"
    ENTRADA = "entrada"  # petiscos, salgados, porções
    LANCHE = "lanche"  # sanduíches, burgers, wraps, tapiocas
    PAES = "paes"
    FRIOS_LATICINIOS = "frios_laticinios"  # frios, queijos e pastas para pão
    HORTIFRUTI = "hortifruti"
    SOBREMESA = "sobremesa"
    BEBIDA = "bebida"  # não alcoólica
    BEBIDA_ALCOOLICA = "bebida_alcoolica"
    UTENSILIOS = "utensilios"  # carvão, gelo, descartáveis


class SpiceLevel(IntEnum):
    NENHUMA = 0
    LEVE = 1
    MEDIA = 2
    ALTA = 3


class Store(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    type: str
    description: str
    delivery_fee: float = Field(ge=0)


class Item(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    store_id: str
    name: str
    description: str
    category: Category
    price: float = Field(gt=0, description="Preço da unidade em reais.")
    unit: str = Field(description="Como o item é vendido, ex.: 'kg', 'lata 350 ml'.")
    serves: float = Field(gt=0, description="Quantas pessoas uma unidade atende.")
    diet: list[DietTag] = Field(default_factory=list)
    spice_level: SpiceLevel = SpiceLevel.NENHUMA

    @model_validator(mode="after")
    def _vegano_implica_vegetariano_e_sem_lactose(self) -> Item:
        tags = set(self.diet)
        if DietTag.VEGANO in tags and not {DietTag.VEGETARIANO, DietTag.SEM_LACTOSE} <= tags:
            raise ValueError(f"{self.id}: item vegano precisa ser vegetariano e sem lactose")
        return self

    def satisfies(self, restrictions: set[DietTag]) -> bool:
        """True se o item atende a todas as restrições pedidas."""
        return restrictions <= set(self.diet)


class Catalog(BaseModel):
    version: str
    stores: list[Store]
    items: list[Item]

    _items_by_id: dict[str, Item] = PrivateAttr(default_factory=dict)
    _stores_by_id: dict[str, Store] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _ids_unicos_e_lojas_existentes(self) -> Catalog:
        store_ids = [s.id for s in self.stores]
        if len(store_ids) != len(set(store_ids)):
            raise ValueError("ids de loja duplicados")
        item_ids = [i.id for i in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("ids de item duplicados")
        unknown = {i.store_id for i in self.items} - set(store_ids)
        if unknown:
            raise ValueError(f"itens apontam para lojas inexistentes: {unknown}")
        return self

    def model_post_init(self, context: object, /) -> None:
        self._items_by_id = {i.id: i for i in self.items}
        self._stores_by_id = {s.id: s for s in self.stores}

    def get_item(self, item_id: str) -> Item | None:
        return self._items_by_id.get(item_id)

    def get_store(self, store_id: str) -> Store | None:
        return self._stores_by_id.get(store_id)
