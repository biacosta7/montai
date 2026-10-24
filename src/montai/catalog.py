"""Carregamento do catálogo.

O catálogo é a única fonte da verdade sobre itens, preços e restrições.
Qualquer id que não esteja aqui não existe para o Montaí.
"""

from functools import lru_cache
from pathlib import Path

from montai.config import CATALOG_PATH
from montai.models import Catalog


@lru_cache(maxsize=4)
def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    return Catalog.model_validate_json(path.read_text(encoding="utf-8"))
