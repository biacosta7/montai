# Avaliação da busca semântica

15 consultas com gabarito em `data/eval/retrieval.json`.

| Configuração | recall@5 | MRR |
|---|---|---|
| minilm | 0.530 | 0.691 |
| e5-small | 0.800 | 0.897 |
| minilm + atributos | 0.570 | 0.608 |
| e5-small + atributos | 0.800 | 0.897 |

## recall@5 por consulta

| Consulta | minilm | e5-small | minilm + atributos | e5-small + atributos |
|---|---|---|---|---|
| r01: carvão para churrasqueira | 1.00 | 0.75 | 0.75 | 0.75 |
| r02: picanha para churrasco | 0.50 | 1.00 | 0.50 | 1.00 |
| r03: cerveja sem glúten | 0.00 | 1.00 | 0.00 | 1.00 |
| r04: pão sem glúten | 1.00 | 1.00 | 1.00 | 1.00 |
| r05: café para servir a equipe no escritório | 0.67 | 0.33 | 0.67 | 0.33 |
| r06: comida tailandesa apimentada | 0.00 | 0.40 | 0.20 | 0.40 |
| r07: hambúrguer vegano | 0.50 | 1.00 | 1.00 | 1.00 |
| r08: kit de café da manhã para várias pessoas | 1.00 | 1.00 | 1.00 | 1.00 |
| r09: refrigerante 2 litros | 0.20 | 1.00 | 0.60 | 1.00 |
| r10: frutas cortadas para o escritório | 0.20 | 0.80 | 0.20 | 0.80 |
| r11: docinhos de festa como brigadeiro | 0.80 | 0.80 | 0.80 | 0.80 |
| r12: macarrão | 0.25 | 0.75 | 0.00 | 0.75 |
| r13: salgados fritos para festa | 0.33 | 0.67 | 0.33 | 0.67 |
| r14: bebida sem álcool para brindar | 1.00 | 1.00 | 1.00 | 1.00 |
| r15: sushi vegetariano | 0.50 | 0.50 | 0.50 | 0.50 |

## Itens que faltaram no top 5

**minilm**

- r02 (picanha para churrasco): faltou churrascaria-001; veio acougue-001, acougue-023, acougue-014, churrascaria-008, padaria-020
- r03 (cerveja sem glúten): faltou mercado-011, adega-006; veio mercado-012, adega-003, adega-007, adega-012, adega-011
- r05 (café para servir a equipe no escritório): faltou graofino-022; veio graofino-001, graofino-002, padaria-013, graofino-021, padaria-014
- r06 (comida tailandesa apimentada): faltou bangkok-004, bangkok-005, bangkok-007, bangkok-013, bangkok-014, bangkok-006; veio bangkok-001, bangkok-015, bangkok-002, bangkok-016, bangkok-011
- r07 (hambúrguer vegano): faltou mercado-033; veio chapa-006, chapa-003, acougue-014, padaria-022, chapa-007
- r09 (refrigerante 2 litros): faltou mercado-001, mercado-003, churrascaria-021, nonna-029, chapa-019, adega-017; veio chapa-018, mercado-004, mercado-006, mercado-012, mercado-002
- r10 (frutas cortadas para o escritório): faltou graofino-020, hortifruti-015, padaria-030, verdevida-025; veio hortifruti-014, doceria-009, doceria-004, hortifruti-021, verdevida-021
- r11 (docinhos de festa como brigadeiro): faltou doceria-009; veio doceria-019, doceria-007, doceria-008, doceria-010, doceria-001
- r12 (macarrão): faltou bangkok-001, bangkok-002, bangkok-003; veio massamia-009, massamia-011, kenzo-007, sahara-010, churrascaria-004
- r13 (salgados fritos para festa): faltou padaria-024, sahara-005; veio padaria-025, acougue-001, chapa-012, verdevida-005, acougue-014
- r15 (sushi vegetariano): faltou kenzo-009; veio kenzo-005, kenzo-020, kenzo-017, kenzo-014, kenzo-016

**e5-small**

- r01 (carvão para churrasqueira): faltou mercado-014; veio mercado-015, acougue-024, acougue-021, acougue-022, churrascaria-010
- r05 (café para servir a equipe no escritório): faltou padaria-013, graofino-022; veio graofino-001, graofino-002, graofino-003, hortifruti-014, graofino-021
- r06 (comida tailandesa apimentada): faltou bangkok-004, bangkok-005, bangkok-007, bangkok-006; veio bangkok-001, bangkok-002, bangkok-012, bangkok-013, bangkok-014
- r10 (frutas cortadas para o escritório): faltou padaria-030; veio hortifruti-014, graofino-001, verdevida-025, graofino-020, hortifruti-015
- r11 (docinhos de festa como brigadeiro): faltou doceria-009; veio doceria-019, doceria-007, doceria-008, doceria-010, doceria-002
- r12 (macarrão): faltou massamia-009; veio bangkok-002, bangkok-001, bangkok-003, bangkok-007, massamia-011
- r13 (salgados fritos para festa): faltou sahara-005; veio padaria-025, hortifruti-017, padaria-024, hortifruti-015, adega-022
- r15 (sushi vegetariano): faltou kenzo-009; veio kenzo-005, kenzo-015, kenzo-022, kenzo-014, kenzo-020

**minilm + atributos**

- r01 (carvão para churrasqueira): faltou acougue-021; veio acougue-022, mercado-015, sahara-011, acougue-024, mercado-014
- r02 (picanha para churrasco): faltou churrascaria-001; veio churrascaria-008, padaria-020, churrascaria-007, acougue-001, lapicante-005
- r03 (cerveja sem glúten): faltou mercado-011, adega-006; veio adega-003, mercado-012, lapicante-021, adega-011, graofino-024
- r05 (café para servir a equipe no escritório): faltou graofino-022; veio graofino-001, graofino-002, padaria-013, graofino-021, graofino-003
- r06 (comida tailandesa apimentada): faltou bangkok-004, bangkok-005, bangkok-013, bangkok-014, bangkok-006; veio bangkok-001, bangkok-015, bangkok-016, bangkok-009, bangkok-007
- r09 (refrigerante 2 litros): faltou mercado-003, churrascaria-021, nonna-029, adega-017; veio mercado-004, chapa-018, mercado-002, mercado-001, chapa-019
- r10 (frutas cortadas para o escritório): faltou graofino-020, hortifruti-015, padaria-030, verdevida-025; veio hortifruti-014, doceria-004, doceria-009, hortifruti-009, hortifruti-021
- r11 (docinhos de festa como brigadeiro): faltou doceria-009; veio doceria-019, doceria-007, doceria-008, doceria-010, doceria-001
- r12 (macarrão): faltou massamia-009, bangkok-001, bangkok-002, bangkok-003; veio massamia-011, churrascaria-004, padaria-010, sahara-010, padaria-009
- r13 (salgados fritos para festa): faltou padaria-024, sahara-005; veio padaria-025, chapa-012, acougue-001, padaria-020, verdevida-005
- r15 (sushi vegetariano): faltou kenzo-009; veio kenzo-005, kenzo-017, kenzo-015, kenzo-019, kenzo-014

**e5-small + atributos**

- r01 (carvão para churrasqueira): faltou mercado-014; veio mercado-015, acougue-024, acougue-021, acougue-022, acougue-023
- r05 (café para servir a equipe no escritório): faltou padaria-013, graofino-021; veio graofino-001, graofino-002, graofino-003, hortifruti-014, graofino-022
- r06 (comida tailandesa apimentada): faltou bangkok-004, bangkok-005, bangkok-007, bangkok-006; veio bangkok-001, bangkok-002, bangkok-012, bangkok-014, bangkok-013
- r10 (frutas cortadas para o escritório): faltou padaria-030; veio hortifruti-014, graofino-001, verdevida-025, hortifruti-015, graofino-020
- r11 (docinhos de festa como brigadeiro): faltou doceria-009; veio doceria-019, doceria-008, doceria-007, doceria-010, doceria-002
- r12 (macarrão): faltou massamia-009; veio bangkok-002, bangkok-001, bangkok-003, bangkok-007, massamia-011
- r13 (salgados fritos para festa): faltou sahara-005; veio padaria-025, hortifruti-017, padaria-024, hortifruti-015, hortifruti-021
- r15 (sushi vegetariano): faltou kenzo-009; veio kenzo-005, kenzo-015, kenzo-022, kenzo-018, kenzo-019
