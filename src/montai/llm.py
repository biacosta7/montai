"""Cliente LLM fino sobre o SDK oficial da OpenAI.

Responsabilidades:
- falar com qualquer provedor compatível (Groq, Gemini, OpenRouter, Ollama);
- registrar tokens e custo estimado no Step corrente;
- obter saídas estruturadas validadas por Pydantic (`structured`).

Não há framework aqui de propósito: são ~100 linhas que dá para ler inteiras.
"""

from __future__ import annotations

import copy
from typing import Any, TypeVar

import openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from montai.config import LLMSettings
from montai.tracing import Step

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def strict_json_schema(model: type[BaseModel]) -> dict:
    """JSON Schema no formato exigido pelo modo estrito de structured outputs.

    No modo estrito o provedor restringe a geração de tokens ao schema
    (constrained decoding), e a resposta sempre é um JSON válido nesse formato.
    As exigências são: todo objeto com `additionalProperties: false` e todos
    os campos listados em `required`. Os modelos expostos ao LLM não têm
    valores padrão, então essa conversão não muda o significado deles.
    """
    schema = copy.deepcopy(model.model_json_schema())
    defs = schema.get("$defs", {})

    def collapse_optional(node: dict) -> None:
        # Pydantic escreve `X | None` como anyOf [X, {"type": "null"}]. O modo
        # estrito do Groq recusa esse anyOf, mas aceita a forma equivalente
        # {"type": [X, "null"]} (ou um enum que inclui null).
        branches = node.get("anyOf")
        if not branches or len(branches) != 2 or {"type": "null"} not in branches:
            return
        other = next(b for b in branches if b != {"type": "null"})
        if "$ref" in other:
            other = copy.deepcopy(defs[other["$ref"].split("/")[-1]])
        if "type" not in other or not isinstance(other["type"], str):
            return
        del node["anyOf"]
        node.update(other)
        node["type"] = [other["type"], "null"]
        if "enum" in node:
            node["enum"] = [*node["enum"], None]

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            collapse_optional(node)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema


class LLMClient:
    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings.from_env()
        if not self.settings.api_key:
            raise LLMError("LLM_API_KEY não configurada. Copie .env.example para .env e preencha.")
        # max_retries: o SDK já reenvia com espera crescente em erros 429
        # (limite de taxa) e 5xx, respeitando o cabeçalho retry-after.
        self.client = OpenAI(
            base_url=self.settings.base_url, api_key=self.settings.api_key, max_retries=6
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

        response = self.client.chat.completions.create(**kwargs)
        usage = response.usage
        if step is not None and usage is not None:
            step.add_usage(
                usage.prompt_tokens,
                usage.completion_tokens,
                self.cost(usage.prompt_tokens, usage.completion_tokens),
            )
        return response.choices[0].message

    def structured(
        self, messages: list[dict], schema: type[T], *, step: Step | None = None, attempts: int = 3
    ) -> T:
        """Pede uma resposta no formato `schema` e valida com Pydantic.

        O "modo estrito" do Groq não restringe a geração: ele valida depois e,
        se o JSON não bate com o schema, devolve erro 400 (json_validate_failed)
        com a geração que falhou. Tratamos esse erro igual a um JSON que não
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
                if body.get("code") != "json_validate_failed":
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
