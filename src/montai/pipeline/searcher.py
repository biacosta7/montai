"""Buscador: para cada necessidade da especificação, busca candidatos.

Não usa LLM. As restrições da especificação viram filtros exatos; a consulta
de cada necessidade ordena os resultados por similaridade.
"""

from __future__ import annotations

from pydantic import BaseModel

from montai.models import CategoryNeed, Item, OrderSpec
from montai.retrieval import Retriever, SearchFilters

CANDIDATES_PER_NEED = 6
CANDIDATES_PER_DIET_OPTION = 3


class NeedCandidates(BaseModel):
    need: CategoryNeed
    items: list[Item]
    scores: dict[str, float]


def search_candidates(spec: OrderSpec, retriever: Retriever) -> list[NeedCandidates]:
    results = []
    for need in spec.needs:
        base = SearchFilters(
            categories=[need.category],
            diet=spec.diet,
            max_spice=spec.max_spice,
            # Um item cuja unidade já custa mais que o orçamento nunca cabe.
            max_price=spec.budget,
        )
        hits = retriever.search(need.query, base, k=CANDIDATES_PER_NEED)

        # Para "uma opção vegana", garante que haja candidatos veganos na lista,
        # mesmo que não estejam entre os mais parecidos com a consulta.
        for option in spec.diet_options:
            extra = base.model_copy(update={"diet": [*spec.diet, option]})
            hits += retriever.search(need.query, extra, k=CANDIDATES_PER_DIET_OPTION)

        unique = {h.item.id: h for h in hits}
        results.append(NeedCandidates(
            need=need,
            items=[h.item for h in unique.values()],
            scores={item_id: h.score for item_id, h in unique.items()},
        ))
    return results
