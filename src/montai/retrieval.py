"""Busca semântica com filtros sobre o catálogo.

Como funciona:
1. Cada item vira um texto ("nome. descrição. categoria. loja") e um vetor
   (embedding) gerado localmente com sentence-transformers, sem custo de API.
2. Os vetores ficam no ChromaDB junto com metadados (categoria, preço,
   picância, uma flag booleana por tag de dieta).
3. Na busca, os filtros viram uma cláusula `where` do Chroma, aplicada antes
   do ranqueamento. Assim, um item com glúten nunca aparece numa busca
   "sem glúten", por mais parecido que seja com a consulta.

Os filtros são exatos (metadados) e o ranqueamento é semântico (vetores).
Restrição alimentar é regra dura, não "parecido com".
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.config import Settings
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

from montai.catalog import load_catalog
from montai.config import DEFAULT_EMBEDDING, EMBEDDING_MODELS, INDEX_DIR, EmbeddingModel
from montai.models import Catalog, Category, DietTag, Item, SpiceLevel


class SearchFilters(BaseModel):
    categories: list[Category] = Field(default_factory=list)
    diet: list[DietTag] = Field(default_factory=list)
    max_price: float | None = None
    max_spice: SpiceLevel | None = None
    store_ids: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    item: Item
    score: float = Field(description="Similaridade de cosseno entre consulta e item (0 a 1).")


@lru_cache(maxsize=2)
def _load_encoder(model_name: str) -> SentenceTransformer:
    # Cacheado: carregar o modelo leva segundos e só precisa acontecer uma vez.
    return SentenceTransformer(model_name)


DIET_LABELS = {
    DietTag.VEGANO: "vegano",
    DietTag.VEGETARIANO: "vegetariano",
    DietTag.SEM_GLUTEN: "sem glúten",
    DietTag.SEM_LACTOSE: "sem lactose",
}
SPICE_LABELS = {
    SpiceLevel.LEVE: "levemente apimentado",
    SpiceLevel.MEDIA: "apimentado",
    SpiceLevel.ALTA: "muito apimentado",
}


def item_document(item: Item, catalog: Catalog, enrich: bool = True) -> str:
    """Texto que representa o item no índice.

    Com `enrich`, os atributos estruturados (dieta e picância) também entram no
    texto. Sem isso, o embedding não "enxerga" que um curry é picante ou que
    um hossomaki de pepino é vegetariano, porque a descrição não diz.
    """
    store = catalog.get_store(item.store_id)
    category = item.category.value.replace("_", " ")
    text = f"{item.name}. {item.description} Categoria: {category}. Loja: {store.name} ({store.type})."
    if enrich:
        if item.diet:
            text += " Dieta: " + ", ".join(DIET_LABELS[t] for t in item.diet) + "."
        # Só descrevemos picância quando ela existe. Escrever "não apimentado"
        # em 390 itens piora a busca: embeddings lidam mal com negação e passam
        # a achar todos eles parecidos com "apimentado".
        if item.spice_level > SpiceLevel.NENHUMA:
            text += f" {SPICE_LABELS[item.spice_level].capitalize()}."
    return text


def item_metadata(item: Item) -> dict:
    # O Chroma só aceita valores escalares em metadados, então cada tag de
    # dieta vira uma flag booleana própria.
    meta = {
        "store_id": item.store_id,
        "category": item.category.value,
        "price": item.price,
        "spice_level": int(item.spice_level),
    }
    for tag in DietTag:
        meta[tag.value] = tag in item.diet
    return meta


def build_where(filters: SearchFilters | None) -> dict | None:
    """Traduz os filtros para a sintaxe `where` do Chroma."""
    if filters is None:
        return None
    conditions: list[dict] = []
    if filters.categories:
        conditions.append({"category": {"$in": [c.value for c in filters.categories]}})
    for tag in filters.diet:
        conditions.append({tag.value: True})
    if filters.max_price is not None:
        conditions.append({"price": {"$lte": filters.max_price}})
    if filters.max_spice is not None:
        conditions.append({"spice_level": {"$lte": int(filters.max_spice)}})
    if filters.store_ids:
        conditions.append({"store_id": {"$in": filters.store_ids}})

    # O Chroma exige pelo menos duas condições dentro de "$and".
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


class Retriever:
    def __init__(
        self,
        catalog: Catalog | None = None,
        embedding: str = DEFAULT_EMBEDDING,
        enrich: bool = True,
        index_dir: Path = INDEX_DIR,
    ) -> None:
        self.catalog = catalog or load_catalog()
        self.model: EmbeddingModel = EMBEDDING_MODELS[embedding]
        self.encoder = _load_encoder(self.model.name)
        self._documents = [item_document(i, self.catalog, enrich) for i in self.catalog.items]
        self._metadatas = [item_metadata(i) for i in self.catalog.items]

        client = chromadb.PersistentClient(
            path=str(index_dir), settings=Settings(anonymized_telemetry=False)
        )
        self.collection = client.get_or_create_collection(
            name=self._collection_name(),
            configuration={"hnsw": {"space": "cosine"}},
            embedding_function=None,  # nós mesmos geramos os vetores
        )
        if self.collection.count() != len(self.catalog.items):
            self._index_catalog()

    def _collection_name(self) -> str:
        # O nome do índice carrega uma impressão digital de tudo que gera os
        # vetores: modelo, prefixo, textos e metadados. Se qualquer coisa mudar,
        # um índice novo é criado. (Uma versão anterior usava só o hash do
        # catálogo, e uma mudança no texto dos documentos reaproveitava vetores
        # velhos sem avisar.)
        fingerprint = hashlib.sha256()
        fingerprint.update(f"{self.model.name}|{self.model.doc_prefix}".encode())
        for doc, meta in zip(self._documents, self._metadatas, strict=True):
            fingerprint.update(f"{doc}|{sorted(meta.items())}".encode())
        model_slug = re.sub(r"[^a-zA-Z0-9]+", "-", self.model.name.split("/")[-1]).strip("-")
        return f"items-{model_slug}-{fingerprint.hexdigest()[:12]}"

    def _encode(self, texts: list[str]) -> list[list[float]]:
        # Vetores normalizados: a distância de cosseno fica entre 0 e 2 e
        # similaridade = 1 - distância.
        return self.encoder.encode(texts, normalize_embeddings=True).tolist()

    def _index_catalog(self) -> None:
        self.collection.upsert(
            ids=[i.id for i in self.catalog.items],
            documents=self._documents,
            embeddings=self._encode([self.model.doc_prefix + d for d in self._documents]),
            metadatas=self._metadatas,
        )

    def search(self, query: str, filters: SearchFilters | None = None, k: int = 5) -> list[SearchHit]:
        result = self.collection.query(
            query_embeddings=self._encode([self.model.query_prefix + query]),
            n_results=k,
            where=build_where(filters),
            include=["distances"],
        )
        hits = []
        for item_id, distance in zip(result["ids"][0], result["distances"][0], strict=True):
            item = self.catalog.get_item(item_id)
            if item is not None:  # defensivo: o índice nunca deve ter id fora do catálogo
                hits.append(SearchHit(item=item, score=round(1 - distance, 4)))
        return hits
