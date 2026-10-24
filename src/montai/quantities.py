"""Regras de quantidade por número de pessoas.

Cada item tem `serves`: quantas pessoas UMA unidade atende. A partir disso:
- units_needed: quantas unidades de um item alimentam N pessoas;
- coverage: quantas pessoas um conjunto de linhas atende;
- max_reasonable_coverage: a partir de quanto a quantidade vira desperdício.
"""

from __future__ import annotations

import math

EPSILON = 1e-9  # evita que 5 / (1/3) = 15.000000000000002 vire 16 unidades


def units_needed(people: int, serves: float) -> int:
    return max(1, math.ceil(people / serves - EPSILON))


def max_reasonable_coverage(people: int, largest_unit_serves: float) -> float:
    """Limite de cobertura antes de ser considerado excesso.

    O dobro das pessoas, ou "o necessário mais uma unidade grande", o que for
    maior. A segunda parte existe porque itens grandes são indivisíveis: um bolo
    que serve 12 é aceitável para 2 pessoas, mas três bolos não.
    """
    return max(2 * people, people + largest_unit_serves)
