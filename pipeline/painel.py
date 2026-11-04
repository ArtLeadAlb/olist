"""Painel Olist: leitura dos marts, formatação e gráficos. Não importa streamlit.

A página (app.py) só monta o layout com o que este módulo entrega. Executar a
página: uv run streamlit run app.py

SPEC (e o porquê de cada regra)

1. LEITURA
   ler(marts) -> dict nome -> DataFrame. Para cada nome, só
   SELECT * FROM marts.<nome>. Nenhuma outra SQL. Conexão com
   duckdb.connect(banco, read_only=True), aberta e fechada dentro de ler().
   Por quê: conexão aberta segura o arquivo, e o pipeline.marts não consegue
   gravar com o painel de pé.

2. NENHUM CÁLCULO
   Proibido em painel.py e app.py: agrupar, somar, tirar média, contar,
   juntar tabelas, reorganizar linhas em colunas e qualquer conta entre
   colunas. Permitido: ordenar, filtrar linhas, pegar as n primeiras,
   renomear coluna e formatar texto.
   Por quê: número novo na tela exige um .sql novo em marts. Se faltar algum
   número, pare e diga qual mart está faltando.
   Única conta permitida: o cartão Recompra (pct_recompra), porque o mart 05
   guarda o complemento (quem comprou uma vez só). Se preferir, crie a coluna
   no mart.

3. LAYOUT (app.py), de cima para baixo, layout="wide"
   Cabeçalho: título "Olist · visão da operação" à esquerda; à direita, o
   filtro de período (item 5).
   Faixa 1: sete cartões (st.metric), nesta ordem, cada rótulo com a
   definição curta:
     Ticket médio (kpis.ticket_medio, reais)
     Cancelados · % de todos os pedidos (kpis.pct_cancelados, 2 casas)
     Peso do frete (kpis.pct_frete, 1 casa)
     Recompra (100 menos recompra.pct_clientes da linha
       pedidos_por_cliente = 1, 2 casas)
     No prazo (entrega_no_prazo.pct_no_prazo, 1 casa)
     Dias até entregar (kpis.dias_entrega, 1 casa)
     Nota média (kpis.nota_media, 2 casas)
   Faixa 2, largura inteira: faturamento mensal, linha com marcadores.
   Faixa 3, três colunas iguais: receita por categoria (top 10, barras
     horizontais, maior em cima); mix de pagamento (barras por pct_valor);
     ticket médio por UF (barras horizontais, maior em cima).
   Faixa 4, três colunas iguais: clientes por UF (barras horizontais, maior
     em cima); nota por categoria (as 10 primeiras por posicao_pior, pontos,
     pior em cima); concentração de vendedores (linha de pct_acumulado por
     posicao, com linha horizontal tracejada em 80).
   Cada gráfico: título com o número do mart ("01 · Faturamento mensal"),
   uma cor só, eixo com unidade. width="stretch" (use_container_width está
   descontinuado).

4. FORMATO: funções puras, sem streamlit e sem banco
   reais(valor, casas=2)  -> "R$ 1.003.862,14"
   pct(valor, casas=1)    -> "93,2%"
   numero(valor, casas=0) -> "96.470"
   Milhar com ponto, decimal com vírgula, sempre, sem usar o locale do
   sistema. Por quê: o resultado não pode depender da máquina de quem roda.
   Uma função por gráfico, recebendo o DataFrame e devolvendo a figura
   plotly. Por quê: o relatório HTML reaproveita as mesmas funções.

5. FILTRO DE PERÍODO
   st.select_slider com os meses de vendas_mensais, padrão de jan/2017 a
   ago/2018. Recorta só as linhas do gráfico de faturamento. Os cartões e os
   outros gráficos não mudam, e a página diz isso embaixo do filtro: "os
   cartões valem para o período inteiro".
   Por quê: recortar linha é SELECT; recalcular cartão por período seria
   regra de negócio fora do SQL.

6. CACHE E ERRO
   Leitura com st.cache_data. Um botão "Recarregar dados" limpa o cache.
   Sem olist.duckdb, ou faltando qualquer mart da lista do item 3: st.error
   dizendo quais e o comando "uv run python -m pipeline.marts", e st.stop().

CRITÉRIOS DE ACEITE
- Os sete cartões mostram: R$ 137,42 · 0,63% · 14,2% · 3,04% · 93,2% ·
  12,5 · 4,09.
- O faturamento abre com 20 meses (jan/2017 a ago/2018) e, com o filtro
  aberto até as pontas, mostra os 24.
- Top 10 de categorias com health_beauty em cima; nota com office_furniture
  em cima; ticket por UF com PB em cima e SP embaixo.
- Uma busca pelos quatro termos de agregação e junção da spec original
  (agrupar, somar, média e juntar, em inglês, como método do pandas) em
  painel.py e app.py não encontra nada. Esta linha não os escreve de
  propósito: citá-los aqui faria a própria busca achá-los.
- Com o painel de pé, uv run python -m pipeline.marts roda sem erro de lock.
"""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px

CAMINHO_BANCO = Path(__file__).resolve().parent / "olist.duckdb"

COR = "#2A6F97"
ALTURA = 520
MESES = ("jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez")


class BancoAusente(Exception):
    pass


class MartsAusentes(Exception):
    def __init__(self, nomes: list[str]):
        super().__init__(", ".join(nomes))
        self.nomes = nomes


# ---------------------------------------------------------------- leitura

def ler(marts: list[str]) -> dict[str, pd.DataFrame]:
    if not CAMINHO_BANCO.is_file():
        raise BancoAusente(str(CAMINHO_BANCO))
    con = duckdb.connect(str(CAMINHO_BANCO), read_only=True)
    try:
        dados, ausentes = {}, []
        for nome in marts:
            try:
                dados[nome] = con.execute(f"SELECT * FROM marts.{nome}").df()
            except duckdb.CatalogException:
                ausentes.append(nome)
    finally:
        con.close()
    if ausentes:
        raise MartsAusentes(ausentes)
    return dados


# ---------------------------------------------------------------- formato

# Em f-string, "," é separador de milhar e "." é decimal, em qualquer máquina.
# Trocar um pelo outro dá o formato brasileiro sem tocar no locale.
_TROCA = str.maketrans(",.", ".,")


def numero(valor, casas: int = 0) -> str:
    return f"{float(valor):,.{casas}f}".translate(_TROCA)


def reais(valor, casas: int = 2) -> str:
    return f"R$ {numero(valor, casas)}"


def pct(valor, casas: int = 1) -> str:
    return f"{numero(valor, casas)}%"


def mes_rotulo(mes) -> str:
    return f"{MESES[mes.month - 1]}/{mes.year}"


# ------------------------------------------------- recortes (sem conta)

def pct_recompra(recompra: pd.DataFrame) -> float:
    """A única conta do painel: o mart 05 guarda quem comprou uma vez só."""
    uma_vez = recompra[recompra["pedidos_por_cliente"] == 1].iloc[0]
    return 100 - uma_vez["pct_clientes"]


def meses(vendas_mensais: pd.DataFrame) -> list:
    # to_datetime só normaliza o tipo da coluna; não calcula nada.
    return list(pd.to_datetime(vendas_mensais["mes"]).drop_duplicates().sort_values())


def periodo_padrao(lista_meses: list) -> tuple:
    inicio, fim = pd.Timestamp("2017-01-01"), pd.Timestamp("2018-08-01")
    return (inicio if inicio in lista_meses else lista_meses[0],
            fim if fim in lista_meses else lista_meses[-1])


def recortar_periodo(vendas_mensais: pd.DataFrame, inicio, fim) -> pd.DataFrame:
    mes = pd.to_datetime(vendas_mensais["mes"])
    return vendas_mensais[(mes >= inicio) & (mes <= fim)]


# ---------------------------------------------------------------- gráficos

def _acabamento(fig, titulo: str, altura: int = ALTURA):
    # separators=",.": decimal com vírgula e milhar com ponto nos eixos e no
    # hover, também sem depender do locale.
    fig.update_layout(title=titulo, height=altura, showlegend=False,
                      separators=",.", margin=dict(t=60, l=10, r=10, b=10))
    return fig


def grafico_faturamento(df: pd.DataFrame):
    fig = px.line(df, x="mes", y="receita", markers=True,
                  color_discrete_sequence=[COR])
    # %m/%Y: o nome do mês em inglês do plotly não serve para este painel.
    fig.update_xaxes(title="Mês de compra", tickformat="%m/%Y")
    fig.update_yaxes(title="Receita (R$)", tickformat=",.0f")
    return _acabamento(fig, "01 · Faturamento mensal", altura=420)


def grafico_categorias(df: pd.DataFrame):
    topo = df.sort_values("receita", ascending=False).head(10)
    fig = px.bar(topo, x="receita", y="categoria", orientation="h",
                 color_discrete_sequence=[COR])
    # reversed: a primeira linha (a maior) fica em cima.
    fig.update_yaxes(title=None, autorange="reversed")
    fig.update_xaxes(title="Receita (R$)", tickformat=",.0f")
    return _acabamento(fig, "02 · Receita por categoria (top 10)")


def grafico_pagamento(df: pd.DataFrame):
    ordenado = df.sort_values("pct_valor", ascending=False)
    fig = px.bar(ordenado, x="tipo", y="pct_valor", color_discrete_sequence=[COR])
    fig.update_xaxes(title="Tipo de pagamento")
    fig.update_yaxes(title="% do valor pago", ticksuffix="%", tickformat=",.0f")
    return _acabamento(fig, "07 · Mix de pagamento")


def grafico_ticket_uf(df: pd.DataFrame):
    ordenado = df.sort_values("ticket_medio", ascending=False)
    fig = px.bar(ordenado, x="ticket_medio", y="uf", orientation="h",
                 color_discrete_sequence=[COR])
    fig.update_yaxes(title=None, autorange="reversed")
    fig.update_xaxes(title="Ticket médio (R$)", tickformat=",.0f")
    return _acabamento(fig, "06 · Ticket médio por UF")


def grafico_clientes_uf(df: pd.DataFrame):
    ordenado = df.sort_values("clientes", ascending=False)
    fig = px.bar(ordenado, x="clientes", y="uf", orientation="h",
                 color_discrete_sequence=[COR])
    fig.update_yaxes(title=None, autorange="reversed")
    fig.update_xaxes(title="Clientes (pessoas)", tickformat=",.0f")
    return _acabamento(fig, "12 · Clientes por UF")


def grafico_nota_categoria(df: pd.DataFrame):
    # categoria como segundo critério: empate na posição não muda a ordem
    # entre execuções.
    piores = df.sort_values(["posicao_pior", "categoria"]).head(10)
    fig = px.scatter(piores, x="nota_media", y="categoria",
                     color_discrete_sequence=[COR])
    fig.update_traces(marker=dict(size=12))
    fig.update_yaxes(title=None, autorange="reversed")
    fig.update_xaxes(title="Nota média (1 a 5)", tickformat=",.2f")
    return _acabamento(fig, "04 · Nota por categoria (10 piores)")


def grafico_vendedores(df: pd.DataFrame):
    ordenado = df.sort_values("posicao")
    fig = px.line(ordenado, x="posicao", y="pct_acumulado",
                  color_discrete_sequence=[COR])
    fig.add_hline(y=80, line_dash="dash", annotation_text="80%",
                  annotation_position="bottom right")
    fig.update_xaxes(title="Vendedores (posição por receita)", tickformat=",.0f")
    fig.update_yaxes(title="% acumulado da receita", ticksuffix="%")
    return _acabamento(fig, "09 · Concentração de vendedores")
