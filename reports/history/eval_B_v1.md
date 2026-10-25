# Avaliação do Montaí

45 pedidos de teste em `data/eval/orders.json`. Versão B: 45 executados (openai/gpt-oss-120b).

## Taxa de acerto por métrica

| | Versão B |
|---|---|
| Classificou possível/impossível certo | 91% (41/45) |
| Respeitou o orçamento | 100% (8/8) |
| Respeitou as restrições | 100% (14/14) |
| Quantidade adequada às pessoas | 100% (37/37) |
| Todos os itens existem no catálogo | 100% (37/37) |
| Pedido resolvido por completo | 91% (41/45) |

Orçamento, restrições, quantidade e catálogo são medidos só nos pedidos em que um carrinho foi entregue; restrições, só nos pedidos que têm alguma.

## Custo e desempenho (média por pedido)

| | Versão B |
|---|---|
| Tokens (entrada + saída) | 4,079 |
| Chamadas ao LLM | 1.8 |
| Latência total (s) | 22.9 |
| Latência mediana (s) | 23.9 |
| Latência sem espera de limite de taxa (s) | 3.3 |
| Custo estimado (US$) | 0.00092 |

## Pedidos resolvidos por grupo

| | Versão B |
|---|---|
| Ocasiões variadas | 93% (13/14) |
| Orçamento apertado | 88% (7/8) |
| Restrições combinadas | 100% (9/9) |
| Impossíveis | 75% (6/8) |
| Ambíguos | 100% (6/6) |

## Resultado por pedido

| Pedido | B |
|---|---|
| o01: quero fazer um churrasco para 5 pessoas, até R$ 200 | ✅ ok |
| o02: jantar leve e sem glúten para 2, nada apimentado | ✅ ok |
| o03: café da manhã para o escritório, 12 pessoas, uma opção vegana | ✅ ok |
| o04: noite de pizza com os amigos, somos 6 | ✅ ok |
| o05: rodízio de sushi em casa para 4 pessoas | ✅ ok |
| o06: aniversário da minha filha, 15 crianças, precisa de bolo e docinhos | ✅ ok |
| o07: almoço de domingo em família, 8 pessoas, comida caseira | ✅ ok |
| o08: happy hour no escritório para 10 pessoas com cerveja e petiscos | ✅ ok |
| o09: lanche da tarde para 3 pessoas | ✅ ok |
| o10: jantar mexicano para 4, pode ser bem apimentado | ✅ ok |
| o11: sessão de filme para 2 com hambúrguer e batata frita | ✅ ok |
| o12: comida árabe para 6 pessoas | ✅ ok |
| o13: jantar romântico italiano para 2, com vinho | ✅ ok |
| o14: almoço tailandês para 3 pessoas | ❌ falhou |
| t01: churrasco para 10 pessoas com R$ 300 | ✅ ok |
| t02: pizza para 4 pessoas, só tenho R$ 110 | ✅ ok |
| t03: almoço para 6 pessoas gastando no máximo R$ 200 | ✅ ok |
| t04: café da manhã para 5 pessoas com R$ 80 | ❌ impossivel |
| t05: comida japonesa para 2 pessoas até R$ 100 | ✅ ok |
| t06: festa para 20 pessoas com salgados e refrigerante, orçamento de R$ 250 | ✅ ok |
| t07: jantar vegano para 3 com R$ 100 | ✅ ok |
| t08: cerveja e petisco para 6 amigos, R$ 120 | ✅ ok |
| c01: jantar vegano e sem glúten para 4 pessoas | ✅ ok |
| c02: almoço sem lactose e sem glúten para 3, nada apimentado | ✅ ok |
| c03: churrasco vegetariano para 6 pessoas | ✅ ok |
| c04: lanche sem glúten para 2 crianças, sem pimenta | ✅ ok |
| c05: sobremesas veganas para uma festa de 10 pessoas | ✅ ok |
| c06: comida japonesa sem glúten para 2 | ✅ ok |
| c07: jantar para 5 pessoas: uma é vegana e outra é celíaca | ✅ ok |
| c08: café da manhã sem lactose para 4 | ✅ ok |
| c09: comida tailandesa vegana para 2, pouco apimentada | ✅ ok |
| i01: churrasco para 20 pessoas com R$ 50 | ✅ impossivel |
| i02: jantar para 4 pessoas com R$ 10 | ✅ impossivel |
| i03: festa de aniversário para 30 pessoas com R$ 60 | ✅ impossivel |
| i04: sushi para 6 pessoas com R$ 40 | ✅ impossivel |
| i05: café da manhã para 50 pessoas com R$ 60 | ✅ impossivel |
| i06: pizza vegana e sem glúten para 2 | ✅ impossivel |
| i07: sushi vegano e sem glúten para 2 pessoas | ❌ ok |
| i08: feijoada vegana para 6 pessoas | ❌ ok |
| a01: algo pra comer hoje à noite | ✅ ok |
| a02: uma festa | ✅ ok |
| a03: comida para o pessoal do trabalho | ✅ ok |
| a04: quero um jantar especial | ✅ ok |
| a05: lanche rápido e barato | ✅ ok |
| a06: churrasco no fim de semana, uns amigos vão aparecer | ✅ ok |

## Falhas

**Versão B** (4)

- o14 (almoço tailandês para 3 pessoas): status falhou
- t04 (café da manhã para 5 pessoas com R$ 80): status impossivel
- i07 (sushi vegano e sem glúten para 2 pessoas): status ok
- i08 (feijoada vegana para 6 pessoas): status ok
