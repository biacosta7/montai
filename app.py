"""Interface web do Montaí: digita um pedido e vê o carrinho e o trace.

Uso: streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from montai.agent_single.agent import run_agent
from montai.llm import LLMClient, QuotaExhausted
from montai.models import CartStatus
from montai.pipeline.orchestrator import run_pipeline
from montai.retrieval import Retriever

STATUS_LABEL = {
    CartStatus.OK: ("success", "Carrinho montado"),
    CartStatus.IMPOSSIBLE: ("warning", "Pedido impossível de atender"),
    CartStatus.FAILED: ("error", "Não foi possível montar um carrinho válido"),
}


@st.cache_resource
def get_retriever() -> Retriever:
    return Retriever()


st.set_page_config(page_title="Montaí", page_icon="🛒", layout="wide")
st.title("Montaí")
st.caption("Descreva o que você precisa e o assistente monta o carrinho.")

with st.form("pedido"):
    order = st.text_area("Pedido", placeholder="churrasco para 5 pessoas, até R$ 200")
    version = st.radio(
        "Versão",
        ["B", "A"],
        horizontal=True,
        format_func=lambda v: {"A": "A: agente único", "B": "B: pipeline"}[v],
    )
    submitted = st.form_submit_button("Montar carrinho", type="primary")

if submitted:
    if not order.strip():
        st.warning("Digite um pedido.")
        st.stop()
    run = run_agent if version == "A" else run_pipeline
    with st.spinner("Montando o carrinho..."):
        try:
            result = run(order, llm=LLMClient(), retriever=get_retriever())
        except QuotaExhausted as exc:
            st.error(f"{exc}. Tente de novo mais tarde.")
            st.stop()
    st.session_state["result"] = result

result = st.session_state.get("result")
if result is not None:
    cart, trace = result.cart, result.trace
    col_cart, col_trace = st.columns([3, 2])

    with col_cart:
        kind, label = STATUS_LABEL[cart.status]
        getattr(st, kind)(label)
        if cart.lines:
            st.dataframe(
                [
                    {
                        "Qtd": line.quantity,
                        "Item": line.name,
                        "Unidade": line.unit,
                        "Loja": line.store_name,
                        "Preço": line.unit_price,
                        "Subtotal": line.subtotal,
                    }
                    for line in cart.lines
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "Preço": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Subtotal": st.column_config.NumberColumn(format="R$ %.2f"),
                },
            )
            m1, m2, m3 = st.columns(3)
            m1.metric("Itens", f"R$ {cart.items_total:.2f}")
            m2.metric("Entrega", f"R$ {cart.delivery_total:.2f}")
            m3.metric("Total", f"R$ {cart.total:.2f}")
            if cart.budget is not None:
                st.caption(f"Orçamento: R$ {cart.budget:.2f}")
        if cart.message:
            st.write(cart.message)
        for problem in cart.problems:
            st.markdown(f"- :red[{problem}]")
        if cart.assumptions:
            st.markdown("**Suposições**")
            for assumption in cart.assumptions:
                st.markdown(f"- {assumption}")

    with col_trace:
        st.subheader("Trace")
        t1, t2, t3 = st.columns(3)
        t1.metric("Tempo", f"{trace.latency_ms / 1000:.1f} s")
        t2.metric("Tokens", trace.tokens_in + trace.tokens_out)
        t3.metric("Custo", f"US$ {trace.cost_usd:.5f}")
        if trace.wait_ms:
            st.caption(f"{trace.wait_ms / 1000:.1f} s esperando limite de taxa do provedor")
        for step in trace.steps:
            tokens = f"{step.tokens_in}+{step.tokens_out} tokens" if step.llm_calls else "sem LLM"
            title = f"{'❌ ' if step.error else ''}{step.name} · {step.latency_ms:.0f} ms · {tokens}"
            with st.expander(title):
                if step.error:
                    st.error(step.error)
                if step.retries:
                    st.caption(f"{step.retries} resposta(s) refeita(s)")
                st.markdown("**Entrada**")
                st.json(step.input, expanded=False)
                st.markdown("**Saída**")
                st.json(step.output, expanded=False)
