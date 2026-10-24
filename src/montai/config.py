"""Caminhos e configurações centrais do projeto."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"
EVAL_DIR = DATA_DIR / "eval"
INDEX_DIR = DATA_DIR / "index"
REPORTS_DIR = ROOT_DIR / "reports"
LOGS_DIR = ROOT_DIR / "logs"

load_dotenv(ROOT_DIR / ".env")


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


@dataclass(frozen=True)
class LLMSettings:
    """Configuração do LLM, lida do ambiente (.env).

    Qualquer provedor com API compatível com a da OpenAI funciona: basta trocar
    base_url, chave e modelo. O código não sabe qual provedor está do outro lado.
    """

    base_url: str
    api_key: str
    model: str
    reasoning_effort: str | None
    # Preço de referência em US$ por milhão de tokens. No plano gratuito o custo
    # real é zero; o valor serve para comparar o custo das versões A e B como
    # se estivessem num plano pago. (Groq, gpt-oss-120b, consultado em out/2026.)
    price_in_per_mtok: float
    price_out_per_mtok: float

    @classmethod
    def from_env(cls) -> "LLMSettings":
        return cls(
            base_url=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=os.getenv("LLM_API_KEY", ""),
            model=os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
            reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "low") or None,
            price_in_per_mtok=float(os.getenv("LLM_PRICE_IN", "0.15")),
            price_out_per_mtok=float(os.getenv("LLM_PRICE_OUT", "0.60")),
        )
