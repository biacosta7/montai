"""Cliente LLM fino sobre o SDK oficial da OpenAI.

Responsabilidades:
- falar com qualquer provedor compatível (Groq, Gemini, OpenRouter, Ollama);
- registrar tokens e custo estimado no Step corrente;
- obter saídas estruturadas validadas por Pydantic (`structured`).

Não há framework aqui de propósito: são ~100 linhas que dá para ler inteiras.
"""

from __future__ import annotations

import copy
import time
from typing import Any, TypeVar

import openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from montai.config import LLMSettings
from montai.tracing import Step

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class QuotaExhausted(RuntimeError):
    """A cota do provedor acabou (ex.: limite diário). Não é falha do pedido.

    Não herda de LLMError de propósito: o pipeline trata LLMError como "não
    consegui montar o carrinho", mas cota esgotada deve interromper a
    avaliação em vez de virar uma falha registrada.
    """

    def __init__(self, wait_s: float) -> None:
        super().__init__(f"cota do provedor esgotada; tente em {wait_s:.0f} s")
        self.wait_s = wait_s


# Erros 400 do Groq que indicam "o modelo gerou algo fora do formato", e não
# um problema na requisição: vale devolver ao modelo e tentar de novo.
RETRYABLE_GENERATION_ERRORS = {"json_validate_failed", "output_parse_failed"}

MAX_ATTEMPTS = 8
MAX_WAIT_S = 90  # pedir para esperar mais que isso indica cota diária, não por minuto


def _retry_after(exc: openai.APIStatusError) -> float | None:
    value = exc.response.headers.get("retry-after") if exc.response is not None else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _walk(node: Any, visit) -> None:
    if isinstance(node, dict):
        visit(node)
        for value in node.values():
            _walk(value, visit)
    elif isinstance(node, list):
        for value in node:
            _walk(value, visit)


def provider_json_schema(model: type[BaseModel]) -> dict:
    """JSON Schema do modelo, ajustado para o que o Groq aceita.

    Pydantic escreve `X | None` como anyOf [X, {"type": "null"}]. O Groq recusa
    esse anyOf (em structured outputs e em parâmetros de ferramenta), mas aceita
    a forma equivalente {"type": [X, "null"]}, ou um enum que inclui null.
    """
    schema = copy.deepcopy(model.model_json_schema())
    defs = schema.get("$defs", {})

    def collapse_optional(node: dict) -> None:
        branches = node.get("anyOf")
        if not branches or len(branches) != 2 or {"type": "null"} not in branches:
            return
        other = next(b for b in branches if b != {"type": "null"})
        if "$ref" in other:
            other = copy.deepcopy(defs[other["$ref"].split("/")[-1]])
        if "type" not in other or not isinstance(other["type"], str):
            return
        del node["anyOf"]
        # Copia só o que restringe o valor; descrições internas da classe não interessam ao modelo.
        node.update({k: v for k, v in other.items() if k not in ("title", "description")})
        node["type"] = [other["type"], "null"]
        if "enum" in node:
            node["enum"] = [*node["enum"], None]

    _walk(schema, collapse_optional)
    return schema


def strict_json_schema(model: type[BaseModel]) -> dict:
    """JSON Schema no formato exigido pelo modo estrito de structured outputs.

    As exigências são: todo objeto com `additionalProperties: false` e todos
    os campos listados em `required`. Os modelos expostos ao LLM não têm
    valores padrão, então essa conversão não muda o significado deles.
    """
    schema = provider_json_schema(model)

    def require_all(node: dict) -> None:
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"])

    _walk(schema, require_all)
    return schema


class LLMClient:
    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings.from_env()
        if not self.settings.api_key:
            raise LLMError("LLM_API_KEY não configurada. Copie .env.example para .env e preencha.")
        # Reenvios ficam com a gente (max_retries=0) para medir quanto tempo foi
        # gasto esperando o limite de taxa, separado do tempo do modelo.
        self.client = OpenAI(
            base_url=self.settings.base_url, api_key=self.settings.api_key, max_retries=0
        )

    @property
    def model(self) -> str:
        return self.settings.model

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        s = self.settings
        return (tokens_in * s.price_in_per_mtok + tokens_out * s.price_out_per_mtok) / 1_000_000

    def chat(
        self,
        messages: list[dict],
        *,
        step: Step | None = None,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
    ):
        """Uma chamada ao modelo. Devolve a mensagem do assistente."""
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        if response_format:
            kwargs["response_format"] = response_format
        if self.settings.reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.reasoning_effort

        response = self._create_with_retries(kwargs, step)
        usage = response.usage
        if step is not None and usage is not None:
            step.add_usage(
                usage.prompt_tokens,
                usage.completion_tokens,
                self.cost(usage.prompt_tokens, usage.completion_tokens),
            )
        return response.choices[0].message

    def _create_with_retries(self, kwargs: dict, step: Step | None):
        for attempt in range(MAX_ATTEMPTS):
            try:
                return self.client.chat.completions.create(**kwargs)
            except openai.RateLimitError as exc:
                wait = _retry_after(exc) or min(2**attempt, 30)
                if wait > MAX_WAIT_S:
                    raise QuotaExhausted(wait) from exc
            except (openai.APIConnectionError, openai.InternalServerError):
                wait = min(2**attempt, 30)
            if step is not None:
                step.wait_ms += wait * 1000
            time.sleep(wait)
        raise LLMError(f"o provedor não respondeu depois de {MAX_ATTEMPTS} tentativas")

    def structured(
        self, messages: list[dict], schema: type[T], *, step: Step | None = None, attempts: int = 3
    ) -> T:
        """Pede uma resposta no formato `schema` e valida com Pydantic.

        O "modo estrito" do Groq não restringe a geração: ele valida depois e,
        se o JSON não bate com o schema, devolve erro 400 (json_validate_failed
        ou output_parse_failed) com a geração que falhou. Tratamos esse erro igual a um JSON que não
        passou no Pydantic: o erro volta ao modelo, que tenta de novo.
        """
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": strict_json_schema(schema), "strict": True},
        }
        history = list(messages)
        last_error = ""
        for _ in range(attempts):
            try:
                message = self.chat(history, step=step, response_format=response_format)
                content = message.content or ""
                return schema.model_validate_json(content)
            except openai.BadRequestError as exc:
                body = exc.body if isinstance(exc.body, dict) else {}
                if body.get("code") not in RETRYABLE_GENERATION_ERRORS:
                    raise
                # Obs.: o provedor não devolve o uso de tokens de uma geração
                # recusada, então essas tentativas não entram no custo estimado.
                content = body.get("failed_generation", "")
                last_error = body.get("message", str(exc))
            except ValidationError as exc:
                last_error = str(exc)
            if step is not None:
                step.retries += 1
            history += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"O JSON não passou na validação:\n{last_error}\nCorrija e responda de novo."},
            ]
        raise LLMError(f"resposta inválida para {schema.__name__}: {last_error}")
