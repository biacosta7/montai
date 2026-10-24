"""Roda um pedido pelo terminal e mostra o carrinho e o trace.

Uso: python scripts/run_order.py "churrasco para 5 pessoas, até R$ 200"
"""

from __future__ import annotations

import argparse
import json

from montai.llm import LLMClient
from montai.pipeline.orchestrator import run_pipeline
from montai.retrieval import Retriever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("order")
    parser.add_argument("--trace", action="store_true", help="mostra entradas e saídas de cada etapa")
    args = parser.parse_args()

    result = run_pipeline(args.order, llm=LLMClient(), retriever=Retriever())
    cart, trace = result.cart, result.trace

    print(f"\nStatus: {cart.status.value}")
    for line in cart.lines:
        print(f"  {line.quantity} x {line.name} ({line.unit}) - {line.store_name} - R$ {line.subtotal:.2f}")
    if cart.lines:
        print(f"  Itens R$ {cart.items_total:.2f} + entrega R$ {cart.delivery_total:.2f} = R$ {cart.total:.2f}")
    print(f"\n{cart.message}")
    for problem in cart.problems:
        print(f"  - {problem}")

    print("\nEtapas:")
    for step in trace.steps:
        tokens = f"{step.tokens_in}+{step.tokens_out} tokens" if step.llm_calls else "sem LLM"
        print(f"  {step.name:<14} {step.latency_ms:>8.0f} ms   {tokens}")
        if args.trace:
            print("    " + json.dumps(step.output, ensure_ascii=False)[:600])
    print(f"Total: {trace.latency_ms / 1000:.1f} s, {trace.tokens_in + trace.tokens_out} tokens, "
          f"US$ {trace.cost_usd:.5f} (estimado)")


if __name__ == "__main__":
    main()
