"""Caminhos e configurações centrais do projeto."""

from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"
EVAL_DIR = DATA_DIR / "eval"
INDEX_DIR = DATA_DIR / "index"
REPORTS_DIR = ROOT_DIR / "reports"


@dataclass(frozen=True)
class EmbeddingModel:
    """Modelo de embeddings e os prefixos que ele espera.

    Modelos da família E5 foram treinados com "query: " e "passage: " na frente
    do texto; sem os prefixos, a qualidade cai. Outros modelos não usam prefixo.
    """

    name: str
    query_prefix: str = ""
    doc_prefix: str = ""


EMBEDDING_MODELS = {
    "minilm": EmbeddingModel("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
    "e5-small": EmbeddingModel(
        "intfloat/multilingual-e5-small", query_prefix="query: ", doc_prefix="passage: "
    ),
}
DEFAULT_EMBEDDING = "e5-small"
