"""Constrói (ou reaproveita) o índice vetorial padrão em data/index/.

O índice não é versionado: ele é derivado do catálogo e pode ser recriado a
qualquer momento. O Retriever também o constrói sozinho na primeira busca;
este script só adianta o trabalho (útil antes de abrir a interface).

Uso: python scripts/build_index.py
"""

from montai.config import DEFAULT_EMBEDDING
from montai.retrieval import Retriever


def main() -> None:
    retriever = Retriever()
    print(f"Índice '{retriever.collection.name}' com {retriever.collection.count()} itens "
          f"(embedding: {DEFAULT_EMBEDDING}).")


if __name__ == "__main__":
    main()
