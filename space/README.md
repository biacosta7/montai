---
title: Montaí
emoji: 🛒
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 8501
short_description: Pedido vago em carrinho de delivery concreto
suggested_hardware: cpu-basic
models:
  - intfloat/multilingual-e5-small
pinned: false
---

# Montaí

**Montaí: an intent-to-cart AI ordering assistant**

Você escreve um pedido vago ("quero fazer um churrasco para 5 pessoas, até R$ 200") e o Montaí monta um carrinho de delivery concreto, respeitando orçamento, número de pessoas e restrições alimentares.

Esta é a demo pública. O código, a avaliação completa (agente único × pipeline) e a documentação estão no GitHub.

- **Pedido novo:** roda a versão A ou B ao vivo. Cada sessão pode fazer até 5 pedidos, porque a chave do LLM está num plano gratuito.
- **Exemplos da avaliação:** execuções reais salvas, que não gastam cota.
