"""Interface do Montaí (Streamlit).

Dois modos:
- Pedido novo: roda a versão A ou B ao vivo, usando o LLM configurado.
- Exemplos da avaliação: mostra execuções salvas em reports/runs/, sem gastar
  cota. Útil na demo pública, quando o plano gratuito do provedor esgota.

Rodar: streamlit run app.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import streamlit as st

# Permite rodar sem instalar o pacote (ex.: Streamlit Community Cloud).
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Em deploy, a chave vem dos secrets da plataforma; localmente, do .env.
try:
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        if key in st.secrets and key not in os.environ:
            os.environ[key] = str(st.secrets[key])
except FileNotFoundError:
    pass

from montai.agent_single.agent import run_agent
from montai.catalog import load_catalog
from montai.eval.metrics import load_cases
from montai.eval.runner import load_records
from montai.llm import LLMClient, LLMError, QuotaExhausted
from montai.models import Cart, CartStatus
from montai.pipeline.orchestrator import run_pipeline
from montai.retrieval import Retriever
from montai.tracing import Step, Trace

EXAMPLES = [
    "quero fazer um churrasco para 5 pessoas, até R$ 200",
    "jantar leve e sem glúten para 2, nada apimentado",
    "café da manhã para o escritório, 12 pessoas, uma opção vegana",
]
VERSIONS = {
    "B": "B · pipeline com papéis",
    "A": "A · agente único",
}
STEP_LABELS = {
    "interpretador": "Interpretador (LLM): pedido → especificação",
    "buscador": "Buscador (código): busca semântica por categoria",
    "pre_checagem": "Pré-checagem (código): o pedido é possível?",
    "montador": "Montador (LLM): escolhe itens e quantidades",
    "validador": "Validador (código): confere regras",
    "agente": "Agente (LLM)",
}

st.set_page_config(page_title="Montaí", page_icon="🛒", layout="centered")


# --- Recursos carregados uma vez por processo -------------------------------


@st.cache_resource(show_spinner="Carregando catálogo e índice de busca...")
def resources():
    catalog = load_catalog()
    return catalog, Retriever(catalog)


@st.cache_resource
def llm_client() -> LLMClient | None:
    try:
        return LLMClient()
    except LLMError:
        return None


# --- Renderização -----------------------------------------------------------


def brl(value: float) -> str:
    # Espaço inseparável: "R$ 69,90" não quebra em duas linhas na tabela.
    return f"R$\u00a0{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def md(text: str) -> str:
    """Escapa "$" para o Streamlit não interpretar "R$ 200 ... R$ 100" como fórmula LaTeX."""
    return text.replace("$", "\\$")


def render_cart(cart: Cart) -> None:
    if cart.status == CartStatus.OK:
        st.success(md(cart.message or "Carrinho montado."), icon="✅")
    elif cart.status == CartStatus.IMPOSSIBLE:
        st.warning(md(f"**Pedido impossível.** {cart.message}"), icon="🚫")
    else:
        st.error(md(f"**Não consegui montar o carrinho.** {cart.message}"), icon="⚠️")

    if cart.lines:
        # Tabela em markdown: leve, responsiva e sem o problema de largura do
        # st.dataframe dentro de abas.
        # Sem coluna de preço unitário: com quantidade e subtotal ela é redundante, e a tabela cabe no celular.
        rows = ["| Qtd | Item | Loja | Subtotal |", "|--:|---|---|--:|"]
        for line in cart.lines:
            # "Picanha (kg)" ajuda; "Kit 2 kg (kit 2 kg)" não: só mostra a unidade se o nome não tem medida.
            item = line.name if re.search(r"\d", line.name) else f"{line.name} ({line.unit})"
            rows.append(
                f"| {line.quantity} | {item} | {line.store_name} | {brl(line.subtotal)} |"
            )
        st.markdown(md("\n".join(rows)))
        cols = st.columns(4)
        cols[0].metric("Itens", brl(cart.items_total))
        cols[1].metric("Entrega", brl(cart.delivery_total))
        cols[2].metric("Total", brl(cart.total))
        cols[3].metric("Orçamento", brl(cart.budget) if cart.budget else "—")

    for problem in cart.problems:
        st.caption(md(f"• {problem}"))
    if cart.assumptions:
        with st.container(border=True):
            st.markdown("**Suposições feitas**")
            for assumption in cart.assumptions:
                st.markdown(md(f"- {assumption}"))


def render_usage(trace: Trace) -> None:
    tokens = f"{trace.tokens_in + trace.tokens_out:,}".replace(",", ".")
    st.caption(
        f"{tokens} tokens · {trace.llm_calls} chamada(s) ao LLM · "
        f"{trace.net_latency_ms / 1000:.1f} s · US$ {trace.cost_usd:.4f} (custo estimado)",
        help="Latência sem a espera por limite de taxa do plano gratuito. O custo usa o preço de "
        "referência de um plano pago; no plano gratuito ele é zero.",
    )


def step_title(step: Step) -> str:
    name = step.name
    label = STEP_LABELS.get(name) or (f"Ferramenta `{name.split(':', 1)[1]}`" if name.startswith("ferramenta:") else name)
    details = [f"{step.latency_ms / 1000:.1f} s"]
    if step.llm_calls:
        details.append(f"{step.tokens_in + step.tokens_out} tokens")
    if step.retries:
        details.append(f"{step.retries} resposta(s) refeita(s)")
    return f"{label} · {' · '.join(details)}"


def render_step(step: Step) -> None:
    st.markdown(f"**{step_title(step)}**")
    if step.error:
        st.error(step.error)
    out = step.output

    if step.name == "buscador" and isinstance(out, dict):
        for category, items in out.items():
            names = ", ".join(f"{i['nome']} ({i['score']:.2f})" for i in items) or "nenhum candidato"
            st.caption(f"**{category}**: {names}")
    elif step.name == "validador" and isinstance(out, dict):
        if out.get("ok"):
            st.markdown(f"✅ aprovado · total {brl(out['total'])}")
        else:
            for problem in out.get("problemas", []):
                st.markdown(md(f"❌ {problem['message']}"))
    elif step.name == "agente" and isinstance(out, dict):
        for call in out.get("chamadas", []):
            st.code(f"{call['ferramenta']}({call['argumentos']})", language="python", wrap_lines=True)
        if out.get("texto"):
            st.markdown(md(f"> {out['texto']}"))
        if out.get("erro"):
            st.caption(f"Erro devolvido ao modelo: {out['erro']}")
    elif step.name == "ferramenta:buscar_itens" and isinstance(out, dict) and "itens" in out:
        found = []
        for row in out["itens"]:
            cells = row.split(" | ")
            found.append(f"{cells[1]} (R$ {cells[4]})")
        st.caption(md(", ".join(found) or "nenhum resultado"))
    elif step.name == "ferramenta:validar_carrinho" and isinstance(out, dict) and "ok" in out:
        st.markdown("✅ aprovado" if out["ok"] else md("❌ " + "; ".join(out["problemas"])))
    else:
        st.json(out, expanded=step.name in ("interpretador", "pre_checagem", "montador"))


def render_trace(trace: Trace) -> None:
    with st.expander(f"Como o Montaí chegou aqui ({len(trace.steps)} etapas)"):
        for step in trace.steps:
            render_step(step)
            st.divider()


def render_result(cart: Cart, trace: Trace) -> None:
    render_cart(cart)
    render_usage(trace)
    render_trace(trace)


# --- Páginas ----------------------------------------------------------------


def page_new_order() -> None:
    catalog, retriever = resources()
    llm = llm_client()
    if llm is None:
        st.info("Configure `LLM_API_KEY` (no `.env` ou nos secrets) para fazer pedidos novos. "
                "Enquanto isso, veja os exemplos da avaliação na barra lateral.")
        return

    version = st.segmented_control(
        "Versão", options=list(VERSIONS), format_func=VERSIONS.get, default="B",
        help="B: Interpretador → Buscador → Montador ⇄ Validador. A: um agente que usa ferramentas.",
    ) or "B"

    def use_example(text: str) -> None:
        st.session_state.order_text = text

    st.caption("Exemplos:")
    for i, example in enumerate(EXAMPLES):
        st.button(example, key=f"example-{i}", on_click=use_example, args=(example,))

    with st.form("order_form"):
        order = st.text_area("O que você quer pedir?", key="order_text", height=80,
                             placeholder="Ex.: jantar vegano para 3 pessoas, até R$ 120")
        submitted = st.form_submit_button("Montar carrinho", type="primary")

    if submitted and order.strip():
        run = run_agent if version == "A" else run_pipeline
        with st.spinner("Montando o carrinho..."):
            try:
                result = run(order.strip(), llm=llm, retriever=retriever, catalog=catalog)
            except QuotaExhausted as exc:
                st.error(f"A cota gratuita do provedor acabou ({exc}). Veja os exemplos salvos na barra lateral.")
                return
        st.session_state.last = (version, result.cart, result.trace)

    if "last" in st.session_state:
        version, cart, trace = st.session_state.last
        st.caption(f"Resultado da versão {VERSIONS[version]}")
        render_result(cart, trace)


def page_saved_runs() -> None:
    st.caption("Execuções reais salvas durante a avaliação (`reports/runs/`). Não gastam cota.")
    cases = {c.id: c for c in load_cases()}
    records = {v: load_records(v) for v in VERSIONS}
    saved = {cid for recs in records.values() for cid in recs}
    available = [cid for cid in cases if cid in saved]
    if not available:
        st.info("Nenhuma execução salva ainda. Rode `python scripts/run_eval.py`.")
        return

    case_id = st.selectbox(
        "Pedido", available, format_func=lambda cid: f"{cid} · {cases[cid].order}" if cid in cases else cid
    )
    versions = [v for v in VERSIONS if case_id in records[v]]
    tabs = st.tabs([VERSIONS[v] for v in versions])
    for tab, version in zip(tabs, versions, strict=True):
        with tab:
            record = records[version][case_id]
            render_result(record.cart, record.trace)


def main() -> None:
    st.title("Montaí")
    st.caption("Montaí: an intent-to-cart AI ordering assistant")

    # Seletor na área principal (e não na barra lateral), para aparecer também no celular.
    page = st.segmented_control(
        "Modo", ["Pedido novo", "Exemplos da avaliação"], default="Pedido novo", label_visibility="collapsed"
    ) or "Pedido novo"

    with st.sidebar:
        st.markdown(
            "Você descreve o pedido do jeito que falaria; o Montaí monta um carrinho concreto "
            "respeitando orçamento, número de pessoas e restrições.\n\n"
            "Orçamento, restrições e existência dos itens são checados **em código**, nunca "
            "confiados ao modelo."
        )

    if page == "Pedido novo":
        page_new_order()
    else:
        page_saved_runs()


main()
