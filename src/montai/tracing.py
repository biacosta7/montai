"""Log estruturado de cada execução.

Uma execução (um pedido) gera um Trace com uma lista de Steps. Cada Step guarda
entrada, saída, tokens, latência e custo estimado. O mesmo objeto alimenta o
painel da interface, o arquivo de log (JSONL) e as métricas da avaliação:
uma única fonte para "o que aconteceu".
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from montai.config import LOGS_DIR


class Step(BaseModel):
    name: str
    input: Any = None
    output: Any = None
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None

    def add_usage(self, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        self.llm_calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.cost_usd += cost_usd


class Trace(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    version: str
    order: str
    steps: list[Step] = Field(default_factory=list)

    @contextmanager
    def step(self, name: str, input: Any = None) -> Iterator[Step]:
        """Mede uma etapa. Exceções ficam registradas no step e seguem adiante."""
        step = Step(name=name, input=input)
        self.steps.append(step)
        start = time.perf_counter()
        try:
            yield step
        except Exception as exc:
            step.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            step.latency_ms = round((time.perf_counter() - start) * 1000, 1)

    @property
    def tokens_in(self) -> int:
        return sum(s.tokens_in for s in self.steps)

    @property
    def tokens_out(self) -> int:
        return sum(s.tokens_out for s in self.steps)

    @property
    def cost_usd(self) -> float:
        return sum(s.cost_usd for s in self.steps)

    @property
    def latency_ms(self) -> float:
        return sum(s.latency_ms for s in self.steps)

    @property
    def llm_calls(self) -> int:
        return sum(s.llm_calls for s in self.steps)

    def write_jsonl(self, path: Path = LOGS_DIR / "runs.jsonl") -> None:
        """Acrescenta uma linha por etapa ao arquivo de log."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for i, step in enumerate(self.steps):
                record = {"run_id": self.run_id, "version": self.version, "index": i}
                record |= step.model_dump(mode="json")
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
