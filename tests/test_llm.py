"""Testes do cliente LLM sem rede: o método `chat` é substituído por um roteiro."""

import openai
import pytest
from openai._exceptions import httpx2

from montai.config import LLMSettings
from montai.llm import LLMClient, LLMError, QuotaExhausted, strict_json_schema
from montai.models import CartProposal, OrderSpec
from montai.tracing import Step

VALID = '{"feasible": true, "lines": [{"item_id": "acougue-001", "quantity": 2}], "rationale": "ok"}'


class Message:
    def __init__(self, content):
        self.content = content


def json_validate_failed(generation: str) -> openai.BadRequestError:
    request = httpx2.Request("POST", "https://example.test")
    response = httpx2.Response(400, request=request)
    body = {"code": "json_validate_failed", "message": "schema mismatch", "failed_generation": generation}
    return openai.BadRequestError("schema mismatch", response=response, body=body)


@pytest.fixture
def client():
    settings = LLMSettings("https://example.test", "chave-falsa", "modelo", None, 0.15, 0.60)
    return LLMClient(settings)


def scripted(client, outcomes):
    calls = []

    def chat(messages, **kwargs):
        calls.append(messages)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Message(outcome)

    client.chat = chat
    return calls


def test_refaz_quando_provedor_recusa_o_schema(client):
    calls = scripted(client, [json_validate_failed('{"feasible": "talvez"}'), VALID])
    step = Step(name="montador")
    result = client.structured([{"role": "user", "content": "x"}], CartProposal, step=step)
    assert result.lines[0].item_id == "acougue-001"
    assert step.retries == 1
    # A segunda chamada leva a geração recusada e o erro de volta ao modelo.
    assert calls[1][-2]["content"] == '{"feasible": "talvez"}'
    assert "schema mismatch" in calls[1][-1]["content"]


def test_refaz_quando_pydantic_recusa(client):
    scripted(client, ["isto não é json", VALID])
    assert client.structured([], CartProposal).feasible is True


def test_desiste_depois_das_tentativas(client):
    scripted(client, ["ruim", "ruim", "ruim"])
    with pytest.raises(LLMError):
        client.structured([], CartProposal)


def test_outros_erros_400_sobem(client):
    request = httpx2.Request("POST", "https://example.test")
    other = openai.BadRequestError(
        "outro", response=httpx2.Response(400, request=request), body={"code": "invalid_api_key"}
    )
    scripted(client, [other])
    with pytest.raises(openai.BadRequestError):
        client.structured([], CartProposal)


def test_opcional_vira_tipo_com_null():
    props = strict_json_schema(OrderSpec)["properties"]
    assert props["budget"]["type"] == ["number", "null"]
    assert props["max_spice"]["type"] == ["integer", "null"]
    assert None in props["max_spice"]["enum"]
    assert "anyOf" not in props["max_spice"]


def test_custo_estimado(client):
    assert client.cost(1_000_000, 1_000_000) == pytest.approx(0.75)


def rate_limited(retry_after: str) -> openai.RateLimitError:
    request = httpx2.Request("POST", "https://example.test")
    response = httpx2.Response(429, request=request, headers={"retry-after": retry_after})
    return openai.RateLimitError("limite", response=response, body={})


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    def create(self, **kwargs):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def fake_sdk(client, outcomes):
    class Chat:
        completions = FakeCompletions(outcomes)

    class SDK:
        chat = Chat()

    client.client = SDK()


def test_espera_limite_por_minuto_e_registra_espera(client, monkeypatch):
    slept = []
    monkeypatch.setattr("montai.llm.time.sleep", slept.append)
    ok = object()
    fake_sdk(client, [rate_limited("2"), ok])
    step = Step(name="x")
    assert client._create_with_retries({}, step) is ok
    assert slept == [2.0]
    assert 2000 <= step.wait_ms < 2100  # espera pedida + duração da tentativa que falhou


def test_cota_diaria_interrompe(client, monkeypatch):
    monkeypatch.setattr("montai.llm.time.sleep", lambda s: None)
    fake_sdk(client, [rate_limited("3600")])
    with pytest.raises(QuotaExhausted):
        client._create_with_retries({}, None)


def test_espera_longa_permitida_continua_a_chamada(client, monkeypatch):
    slept = []
    monkeypatch.setattr("montai.llm.time.sleep", slept.append)
    client.max_wait_s = 3600
    ok = object()
    fake_sdk(client, [rate_limited("900"), rate_limited("900"), ok])
    assert client._create_with_retries({}, None) is ok
    assert slept == [900.0, 900.0]
