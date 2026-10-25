# Avaliação do Montaí

45 pedidos de teste em `data/eval/orders.json`. Versão B: 10 executados (openai/gpt-oss-120b).

## Taxa de acerto por métrica

| | Versão B |
|---|---|
| Classificou possível/impossível certo | 90% (9/10) |
| Respeitou o orçamento | 100% (1/1) |
| Respeitou as restrições | 100% (2/2) |
| Quantidade adequada às pessoas | 100% (7/7) |
| Todos os itens existem no catálogo | 100% (7/7) |
| Pedido resolvido por completo | 90% (9/10) |

Orçamento, restrições, quantidade e catálogo são medidos só nos pedidos em que um carrinho foi entregue; restrições, só nos pedidos que têm alguma.

## Custo e desempenho (média por pedido)

| | Versão B |
|---|---|
| Tokens (entrada + saída) | 4,728 |
| Chamadas ao LLM | 2.0 |
| Latência total (s) | 75.9 |
| Latência mediana (s) | 16.1 |
| Latência sem espera de limite de taxa (s) | 63.2 |
| Custo estimado (US$) | 0.00100 |

## Pedidos resolvidos por grupo

| | Versão B |
|---|---|
| Ocasiões variadas | 100% (7/7) |
| Orçamento apertado | 0% (0/1) |
| Restrições combinadas | n/a |
| Impossíveis | 100% (2/2) |
| Ambíguos | n/a |

## Resultado por pedido

| Pedido | B |
|---|---|
| o01: quero fazer um churrasco para 5 pessoas, até R$ 200 | ✅ ok |
| o02: jantar leve e sem glúten para 2, nada apimentado | ✅ ok |
| o03: café da manhã para o escritório, 12 pessoas, uma opção vegana | ✅ ok |
| o04: noite de pizza com os amigos, somos 6 | ✅ ok |
| o05: rodízio de sushi em casa para 4 pessoas | ✅ ok |
| o06: aniversário da minha filha, 15 crianças, precisa de bolo e docinhos | ✅ ok |
| o07: almoço de domingo em família, 8 pessoas, comida caseira | - |
| o08: happy hour no escritório para 10 pessoas com cerveja e petiscos | - |
| o09: lanche da tarde para 3 pessoas | - |
| o10: jantar mexicano para 4, pode ser bem apimentado | - |
| o11: sessão de filme para 2 com hambúrguer e batata frita | - |
| o12: comida árabe para 6 pessoas | - |
| o13: jantar romântico italiano para 2, com vinho | - |
| o14: almoço tailandês para 3 pessoas | ✅ ok |
| t01: churrasco para 10 pessoas com R$ 300 | - |
| t02: pizza para 4 pessoas, só tenho R$ 110 | - |
| t03: almoço para 6 pessoas gastando no máximo R$ 200 | - |
| t04: café da manhã para 5 pessoas com R$ 80 | ❌ impossivel |
| t05: comida japonesa para 2 pessoas até R$ 100 | - |
| t06: festa para 20 pessoas com salgados e refrigerante, orçamento de R$ 250 | - |
| t07: jantar vegano para 3 com R$ 100 | - |
| t08: cerveja e petisco para 6 amigos, R$ 120 | - |
| c01: jantar vegano e sem glúten para 4 pessoas | - |
| c02: almoço sem lactose e sem glúten para 3, nada apimentado | - |
| c03: churrasco vegetariano para 6 pessoas | - |
| c04: lanche sem glúten para 2 crianças, sem pimenta | - |
| c05: sobremesas veganas para uma festa de 10 pessoas | - |
| c06: comida japonesa sem glúten para 2 | - |
| c07: jantar para 5 pessoas: uma é vegana e outra é celíaca | - |
| c08: café da manhã sem lactose para 4 | - |
| c09: comida tailandesa vegana para 2, pouco apimentada | - |
| i01: churrasco para 20 pessoas com R$ 50 | - |
| i02: jantar para 4 pessoas com R$ 10 | - |
| i03: festa de aniversário para 30 pessoas com R$ 60 | - |
| i04: sushi para 6 pessoas com R$ 40 | - |
| i05: café da manhã para 50 pessoas com R$ 60 | - |
| i06: pizza vegana e sem glúten para 2 | - |
| i07: sushi vegano e sem glúten para 2 pessoas | ✅ impossivel |
| i08: feijoada vegana para 6 pessoas | ✅ impossivel |
| a01: algo pra comer hoje à noite | - |
| a02: uma festa | - |
| a03: comida para o pessoal do trabalho | - |
| a04: quero um jantar especial | - |
| a05: lanche rápido e barato | - |
| a06: churrasco no fim de semana, uns amigos vão aparecer | - |

## Falhas

**Versão B** (1)

- t04 (café da manhã para 5 pessoas com R$ 80): status impossivel
