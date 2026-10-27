# Avaliação do Montaí

Pedidos de teste em `data/eval/orders.json`. Amostra estratificada: 4 pedidos sorteados por grupo (semente 42), 20 no total. Versão A: 20 executados (openai/gpt-oss-120b), Versão B: 20 executados (openai/gpt-oss-120b).

## Taxa de acerto por métrica

| | Versão A | Versão B |
|---|---|---|
| Classificou possível/impossível certo | 90% (18/20) | 95% (19/20) |
| Respeitou o orçamento | 100% (3/3) | 100% (4/4) |
| Respeitou as restrições | 100% (5/5) | 100% (6/6) |
| Quantidade adequada às pessoas | 100% (14/14) | 100% (15/15) |
| Todos os itens existem no catálogo | 100% (14/14) | 100% (15/15) |
| Pedido resolvido por completo | 90% (18/20) | 95% (19/20) |

Orçamento, restrições, quantidade e catálogo são medidos só nos pedidos em que um carrinho foi entregue; restrições, só nos pedidos que têm alguma.

## Custo e desempenho (média por pedido)

| | Versão A | Versão B |
|---|---|---|
| Tokens (entrada + saída) | 8,014 | 4,396 |
| Chamadas ao LLM | 4.2 | 1.9 |
| **Latência líquida, mediana (s)** | **4.7** | **3.2** |
| Latência líquida, média (s) | 94.7 | 64.0 |
| Latência total com esperas, mediana (s) | 23.9 | 28.3 |
| Execuções com chamada presa no provedor | 3 | 2 |
| Custo estimado (US$) | 0.00139 | 0.00093 |

Latência líquida = tempo total menos as esperas por limite de taxa do plano gratuito. A mediana é a medida principal: algumas chamadas ficaram presas no provedor até o timeout (cerca de 10 min) antes de serem reenviadas, e esses casos distorcem a média.

## Pedidos resolvidos por grupo

| | Versão A | Versão B |
|---|---|---|
| Ocasiões variadas | 100% (4/4) | 100% (4/4) |
| Orçamento apertado | 50% (2/4) | 75% (3/4) |
| Restrições combinadas | 100% (4/4) | 100% (4/4) |
| Impossíveis | 100% (4/4) | 100% (4/4) |
| Ambíguos | 100% (4/4) | 100% (4/4) |

## Resultado por pedido

| Pedido | A | B |
|---|---|---|
| o01: quero fazer um churrasco para 5 pessoas, até R$ 200 | ✅ ok | ✅ ok |
| o02: jantar leve e sem glúten para 2, nada apimentado | ✅ ok | ✅ ok |
| o05: rodízio de sushi em casa para 4 pessoas | ✅ ok | ✅ ok |
| o11: sessão de filme para 2 com hambúrguer e batata frita | ✅ ok | ✅ ok |
| t01: churrasco para 10 pessoas com R$ 300 | ✅ ok | ✅ ok |
| t02: pizza para 4 pessoas, só tenho R$ 110 | ❌ impossivel | ✅ ok |
| t04: café da manhã para 5 pessoas com R$ 80 | ✅ ok | ❌ impossivel |
| t07: jantar vegano para 3 com R$ 100 | ❌ falhou | ✅ ok |
| c02: almoço sem lactose e sem glúten para 3, nada apimentado | ✅ ok | ✅ ok |
| c04: lanche sem glúten para 2 crianças, sem pimenta | ✅ ok | ✅ ok |
| c05: sobremesas veganas para uma festa de 10 pessoas | ✅ ok | ✅ ok |
| c09: comida tailandesa vegana para 2, pouco apimentada | ✅ ok | ✅ ok |
| i01: churrasco para 20 pessoas com R$ 50 | ✅ impossivel | ✅ impossivel |
| i02: jantar para 4 pessoas com R$ 10 | ✅ impossivel | ✅ impossivel |
| i07: sushi vegano e sem glúten para 2 pessoas | ✅ impossivel | ✅ impossivel |
| i08: feijoada vegana para 6 pessoas | ✅ impossivel | ✅ impossivel |
| a01: algo pra comer hoje à noite | ✅ ok | ✅ ok |
| a02: uma festa | ✅ ok | ✅ ok |
| a03: comida para o pessoal do trabalho | ✅ ok | ✅ ok |
| a05: lanche rápido e barato | ✅ ok | ✅ ok |

## Falhas

**Versão A** (2)

- t02 (pizza para 4 pessoas, só tenho R$ 110): status impossivel
- t07 (jantar vegano para 3 com R$ 100): status falhou

**Versão B** (1)

- t04 (café da manhã para 5 pessoas com R$ 80): status impossivel
