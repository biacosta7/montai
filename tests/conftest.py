import pytest

from montai.catalog import load_catalog
from montai.retrieval import Retriever


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


@pytest.fixture(scope="session")
def retriever(tmp_path_factory, catalog):
    return Retriever(catalog, index_dir=tmp_path_factory.mktemp("index"))


class FakeLLM:
    """LLM roteirizado: devolve as respostas na ordem em que foram enfileiradas.

    Permite testar o orquestrador inteiro (inclusive o ciclo de correção) sem
    rede, sem custo e de forma determinística.
    """

    model = "fake"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def structured(self, messages, schema, *, step=None, attempts=2):
        self.calls.append((schema.__name__, messages))
        response = self.responses.pop(0)
        assert isinstance(response, schema), f"esperava {schema.__name__}, veio {type(response).__name__}"
        if step is not None:
            step.add_usage(100, 50, 0.0)
        return response


@pytest.fixture
def fake_llm():
    return FakeLLM
