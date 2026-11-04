"""Página do painel Olist.

Executar: uv run streamlit run app.py
A spec, com o motivo de cada regra, está na docstring de painel.py. Aqui só
há layout: leitura, formatação e gráficos vêm de lá.
"""

import streamlit as st

import painel

# Os marts que a página usa (item 3 da spec). nota_por_prazo e
# tempo_entrega_por_estado existem no banco, mas não aparecem no layout.
MARTS = (
    "kpis", "recompra", "entrega_no_prazo", "vendas_mensais",
    "top_categorias", "mix_pagamento", "ticket_medio_por_estado",
    "clientes_por_uf", "nota_por_categoria", "vendedores_pareto",
)

COMANDO = "uv run python -m pipeline.marts"

st.set_page_config(page_title="Olist · visão da operação", layout="wide")


@st.cache_data(show_spinner=False)
def carregar(marts: tuple) -> dict:
    return painel.ler(list(marts))


col_titulo, col_filtro = st.columns([3, 2])

with col_titulo:
    st.title("Olist · visão da operação")
    # O botão vem antes da leitura: o clique limpa o cache na mesma execução
    # em que os dados são lidos de novo. Fica visível também no erro, para
    # recarregar depois de rodar o pipeline.
    if st.button("Recarregar dados"):
        st.cache_data.clear()

try:
    dados = carregar(MARTS)
except painel.BancoAusente as e:
    st.error(f"Banco não encontrado: {e}. Gere os marts com `{COMANDO}`.")
    st.stop()
except painel.MartsAusentes as e:
    st.error(f"Marts ausentes: {', '.join(e.nomes)}. Gere-os com `{COMANDO}`.")
    st.stop()

# ----------------------------------------------------------- filtro (item 5)
lista_meses = painel.meses(dados["vendas_mensais"])
with col_filtro:
    inicio, fim = st.select_slider(
        "Período do faturamento",
        options=lista_meses,
        value=painel.periodo_padrao(lista_meses),
        format_func=painel.mes_rotulo,
    )
    st.caption("os cartões valem para o período inteiro")

# ------------------------------------------------------------ faixa 1: cartões
kpis = dados["kpis"].iloc[0]
no_prazo = dados["entrega_no_prazo"].iloc[0]

cartoes = [
    ("Ticket médio · por pedido", painel.reais(kpis["ticket_medio"])),
    ("Cancelados · % de todos os pedidos", painel.pct(kpis["pct_cancelados"], 2)),
    ("Peso do frete · % do valor pago", painel.pct(kpis["pct_frete"], 1)),
    ("Recompra · % com 2+ pedidos", painel.pct(painel.pct_recompra(dados["recompra"]), 2)),
    ("No prazo · % até a data prevista", painel.pct(no_prazo["pct_no_prazo"], 1)),
    ("Dias até entregar · da compra", painel.numero(kpis["dias_entrega"], 1)),
    ("Nota média · de 1 a 5", painel.numero(kpis["nota_media"], 2)),
]
for coluna, (rotulo, valor) in zip(st.columns(7), cartoes):
    coluna.metric(rotulo, valor)

# ----------------------------------------------------------- faixa 2: faturamento
recorte = painel.recortar_periodo(dados["vendas_mensais"], inicio, fim)
st.plotly_chart(painel.grafico_faturamento(recorte), width="stretch")

# ------------------------------------------------------------ faixa 3
c1, c2, c3 = st.columns(3)
c1.plotly_chart(painel.grafico_categorias(dados["top_categorias"]), width="stretch")
c2.plotly_chart(painel.grafico_pagamento(dados["mix_pagamento"]), width="stretch")
c3.plotly_chart(painel.grafico_ticket_uf(dados["ticket_medio_por_estado"]), width="stretch")

# ------------------------------------------------------------ faixa 4
c4, c5, c6 = st.columns(3)
c4.plotly_chart(painel.grafico_clientes_uf(dados["clientes_por_uf"]), width="stretch")
c5.plotly_chart(painel.grafico_nota_categoria(dados["nota_por_categoria"]), width="stretch")
c6.plotly_chart(painel.grafico_vendedores(dados["vendedores_pareto"]), width="stretch")
