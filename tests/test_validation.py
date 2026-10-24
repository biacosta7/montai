"""Testes do validador determinístico (regras 1 e 2: o código é o juiz)."""

from montai.models import Category, Constraints, DietTag, ProposalLine, SpiceLevel
from montai.quantities import max_reasonable_coverage, units_needed
from montai.validation import ProblemCode, validate_cart


def lines(*pairs):
    return [ProposalLine(item_id=i, quantity=q) for i, q in pairs]


def codes(report):
    return report.problem_codes()


def test_units_needed():
    assert units_needed(5, 2.5) == 2
    assert units_needed(5, 1 / 3) == 15
    assert units_needed(1, 12) == 1


def test_max_reasonable_coverage():
    assert max_reasonable_coverage(2, 12) == 14  # um bolo inteiro para 2 é aceitável
    assert max_reasonable_coverage(10, 1) == 20


def test_carrinho_valido_com_totais_do_catalogo(catalog):
    # 2 kg de picanha (açougue) + 1 refrigerante 2 L (mercado) para 5 pessoas
    report = validate_cart(
        lines(("acougue-001", 2), ("mercado-001", 1)),
        Constraints(people=5, budget=250, required_categories=[Category.GRELHADOS]),
        catalog,
    )
    assert report.ok, report.problems
    assert report.items_total == round(2 * 94.90 + 10.90, 2)
    assert report.delivery_total == round(7.90 + 5.90, 2)  # uma taxa por loja
    assert report.total == round(report.items_total + report.delivery_total, 2)


def test_item_inexistente(catalog):
    report = validate_cart(lines(("inventado-999", 1)), Constraints(people=1), catalog)
    assert ProblemCode.UNKNOWN_ITEM in codes(report)
    assert ProblemCode.EMPTY_CART in codes(report)
    assert not report.ok


def test_quantidade_invalida(catalog):
    report = validate_cart(lines(("acougue-001", 0)), Constraints(people=1), catalog)
    assert ProblemCode.INVALID_QUANTITY in codes(report)


def test_orcamento_inclui_entrega(catalog):
    # 2 x 94,90 = 189,80 cabe em 190, mas com a entrega de 7,90 não cabe.
    report = validate_cart(lines(("acougue-001", 2)), Constraints(people=5, budget=190), catalog)
    assert ProblemCode.BUDGET_EXCEEDED in codes(report)


def test_restricao_alimentar(catalog):
    report = validate_cart(
        lines(("acougue-018", 1)),  # pão de alho tem glúten
        Constraints(people=5, diet=[DietTag.SEM_GLUTEN]),
        catalog,
    )
    assert ProblemCode.DIET_VIOLATION in codes(report)


def test_utensilios_nao_sao_checados_como_comida(catalog):
    report = validate_cart(
        lines(("hortifruti-018", 3), ("mercado-014", 1)),  # espetinho de legumes + carvão
        Constraints(people=5, diet=[DietTag.VEGANO], required_categories=[Category.GRELHADOS]),
        catalog,
    )
    assert report.ok, report.problems


def test_picancia(catalog):
    report = validate_cart(
        lines(("bangkok-004", 1)),  # curry verde, picância 3
        Constraints(people=1, max_spice=SpiceLevel.NENHUMA),
        catalog,
    )
    assert ProblemCode.SPICE_VIOLATION in codes(report)


def test_opcao_de_dieta(catalog):
    constraints = Constraints(people=2, diet_options=[DietTag.VEGANO])
    sem_opcao = validate_cart(lines(("padaria-008", 2)), constraints, catalog)
    com_opcao = validate_cart(lines(("padaria-008", 1), ("padaria-022", 1)), constraints, catalog)
    assert ProblemCode.MISSING_DIET_OPTION in codes(sem_opcao)
    assert ProblemCode.MISSING_DIET_OPTION not in codes(com_opcao)


def test_quantidade_insuficiente(catalog):
    report = validate_cart(
        lines(("acougue-001", 1)),  # 1 kg serve 2,5 pessoas
        Constraints(people=5, required_categories=[Category.GRELHADOS]),
        catalog,
    )
    assert ProblemCode.INSUFFICIENT_QUANTITY in codes(report)


def test_prato_principal_cobre_categorias_de_comida(catalog):
    report = validate_cart(
        lines(("churrascaria-007", 1)),  # combo churrasco para 4
        Constraints(people=4, required_categories=[Category.GRELHADOS, Category.ACOMPANHAMENTO]),
        catalog,
    )
    assert report.ok, report.problems


def test_prato_principal_nao_cobre_bebida(catalog):
    report = validate_cart(
        lines(("churrascaria-007", 1)),
        Constraints(people=4, required_categories=[Category.BEBIDA]),
        catalog,
    )
    assert ProblemCode.INSUFFICIENT_QUANTITY in codes(report)


def test_quantidade_excessiva(catalog):
    report = validate_cart(lines(("acougue-001", 10)), Constraints(people=2), catalog)
    assert ProblemCode.EXCESSIVE_QUANTITY in codes(report)


def test_linhas_repetidas_sao_somadas(catalog):
    report = validate_cart(lines(("acougue-001", 1), ("acougue-001", 1)), Constraints(people=5), catalog)
    assert len(report.lines) == 1
    assert report.lines[0].quantity == 2
