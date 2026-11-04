"""Testes de painel.py: formatos, recortes, gráficos e leitura dos marts."""

import decimal

import duckdb
import pandas as pd
import pytest

import painel


# ------------------------------------------------------------------ formato

def test_milhar_com_ponto_e_decimal_com_virgula():
    assert painel.numero(1234567.891, 2) == "1.234.567,89"
    assert painel.numero(52000) == "52.000"
    assert painel.numero(1234.5, 1) == "1.234,5"


def test_numero_sem_casas_nao_mostra_virgula():
    assert painel.numero(7) == "7"
    assert painel.numero(999) == "999"
    assert painel.numero(1000) == "1.000"


def test_numero_negativo_mantem_o_sinal():
    assert painel.numero(-1234.5, 1) == "-1.234,5"


def test_numero_aceita_decimal_do_banco():
    assert painel.numero(decimal.Decimal("10.50"), 1) == "10,5"


def test_reais_tem_prefixo_e_duas_casas_por_padrao():
    assert painel.reais(1234567.891) == "R$ 1.234.567,89"
    assert painel.reais(0.5) == "R$ 0,50"


def test_reais_aceita_outro_numero_de_casas():
    assert painel.reais(1234.4, casas=0) == "R$ 1.234"


def test_pct_tem_uma_casa_por_padrao_e_sufixo():
    assert painel.pct(7.0) == "7,0%"
    assert painel.pct(12.5) == "12,5%"


def test_pct_aceita_outro_numero_de_casas():
    assert painel.pct(0.25, casas=2) == "0,25%"


def test_nome_do_mes_em_portugues_sem_depender_do_sistema():
    assert painel.mes_rotulo(pd.Timestamp("2017-01-01")) == "jan/2017"
    assert painel.mes_rotulo(pd.Timestamp("2018-08-15")) == "ago/2018"
    assert painel.mes_rotulo(pd.Timestamp("2016-12-01")) == "dez/2016"


# ------------------------------------------------------------------ recortes e a única conta

def test_recompra_e_o_complemento_da_linha_de_um_pedido():
    recompra = pd.DataFrame({
        "pedidos_por_cliente": [1, 2, 3],
        "clientes": [80, 15, 5],
        "pct_clientes": [80.5, 15.0, 4.5],
    })
    assert painel.pct_recompra(recompra) == 19.5


def test_recompra_ignora_as_linhas_de_dois_pedidos_ou_mais():
    recompra = pd.DataFrame({
        "pedidos_por_cliente": [2, 1],
        "clientes": [10, 90],
        "pct_clientes": [10.0, 90.0],
    })
    assert painel.pct_recompra(recompra) == 10.0


def _vendas_mensais(inicio, fim, como_data):
    meses = pd.date_range(inicio, fim, freq="MS")
    coluna = meses.date if como_data else meses
    return pd.DataFrame({"mes": coluna, "receita": range(len(meses))})


def test_meses_vem_em_ordem_e_sem_repetir():
    df = pd.DataFrame({"mes": pd.to_datetime(["2017-03-01", "2017-01-01", "2017-02-01", "2017-01-01"])})
    assert painel.meses(df) == [
        pd.Timestamp("2017-01-01"), pd.Timestamp("2017-02-01"), pd.Timestamp("2017-03-01"),
    ]


def test_periodo_padrao_vai_de_jan_2017_a_ago_2018():
    lista = painel.meses(_vendas_mensais("2016-12-01", "2018-10-01", como_data=True))
    assert painel.periodo_padrao(lista) == (pd.Timestamp("2017-01-01"), pd.Timestamp("2018-08-01"))


def test_periodo_padrao_cai_nas_pontas_se_o_dado_nao_cobre_o_periodo():
    lista = painel.meses(_vendas_mensais("2019-01-01", "2019-03-01", como_data=False))
    assert painel.periodo_padrao(lista) == (pd.Timestamp("2019-01-01"), pd.Timestamp("2019-03-01"))


def test_recorte_padrao_tem_vinte_meses_e_o_filtro_aberto_mostra_todos():
    df = _vendas_mensais("2016-12-01", "2018-10-01", como_data=True)
    lista = painel.meses(df)
    inicio, fim = painel.periodo_padrao(lista)
    assert len(painel.recortar_periodo(df, inicio, fim)) == 20
    assert len(painel.recortar_periodo(df, lista[0], lista[-1])) == len(lista)


def test_recorte_funciona_com_a_coluna_em_datetime():
    df = _vendas_mensais("2016-12-01", "2018-10-01", como_data=False)
    recorte = painel.recortar_periodo(df, pd.Timestamp("2017-01-01"), pd.Timestamp("2017-03-01"))
    assert list(recorte["receita"]) == [1, 2, 3]


def test_recorte_inclui_os_dois_extremos():
    df = _vendas_mensais("2017-01-01", "2017-05-01", como_data=False)
    recorte = painel.recortar_periodo(df, pd.Timestamp("2017-02-01"), pd.Timestamp("2017-02-01"))
    assert len(recorte) == 1


# ------------------------------------------------------------------ gráficos

def _pontos(fig):
    return len(fig.data[0].x)


def test_faturamento_e_uma_linha_com_marcadores_e_um_ponto_por_mes():
    df = _vendas_mensais("2017-01-01", "2017-05-01", como_data=False)
    fig = painel.grafico_faturamento(df)
    assert _pontos(fig) == 5
    assert "markers" in fig.data[0].mode
    assert len(fig.data) == 1


def test_categorias_mostram_so_as_dez_maiores_com_a_maior_em_cima():
    df = pd.DataFrame({
        "categoria": [f"c{i:02d}" for i in range(12)],
        "receita": [float(i * 100) for i in range(12)],  # c11 é a maior
    })
    fig = painel.grafico_categorias(df)
    assert _pontos(fig) == 10
    assert list(fig.data[0].y)[0] == "c11"
    assert fig.layout.yaxis.autorange == "reversed"


def test_categorias_com_menos_de_dez_linhas_mostram_todas():
    df = pd.DataFrame({"categoria": ["a", "b", "c"], "receita": [3.0, 1.0, 2.0]})
    assert _pontos(painel.grafico_categorias(df)) == 3


def test_pagamento_tem_uma_barra_por_tipo_do_maior_para_o_menor():
    df = pd.DataFrame({"tipo": ["boleto", "cartao", "voucher"], "pct_valor": [20.0, 70.0, 10.0]})
    fig = painel.grafico_pagamento(df)
    assert _pontos(fig) == 3
    assert list(fig.data[0].x) == ["cartao", "boleto", "voucher"]


def test_ticket_por_uf_tem_o_maior_em_cima_e_o_menor_embaixo():
    df = pd.DataFrame({"uf": ["SP", "PB", "RJ", "AC"], "ticket_medio": [90.0, 200.0, 120.0, 150.0]})
    fig = painel.grafico_ticket_uf(df)
    assert _pontos(fig) == 4
    assert list(fig.data[0].y) == ["PB", "AC", "RJ", "SP"]
    assert fig.layout.yaxis.autorange == "reversed"


def test_clientes_por_uf_tem_a_maior_em_cima():
    df = pd.DataFrame({"uf": ["AC", "SP", "RJ"], "clientes": [5, 500, 50]})
    fig = painel.grafico_clientes_uf(df)
    assert _pontos(fig) == 3
    assert list(fig.data[0].y)[0] == "SP"
    assert fig.layout.yaxis.autorange == "reversed"


def test_nota_mostra_as_dez_piores_com_a_pior_em_cima_e_so_pontos():
    df = pd.DataFrame({
        "categoria": [f"c{i:02d}" for i in range(12)],
        "nota_media": [3.0 + i / 10 for i in range(12)],
        "posicao_pior": list(range(12, 0, -1)),  # c11 tem a posição 1, a pior
    })
    fig = painel.grafico_nota_categoria(df)
    assert _pontos(fig) == 10
    assert list(fig.data[0].y)[0] == "c11"
    assert fig.data[0].mode == "markers"
    assert fig.layout.yaxis.autorange == "reversed"


def test_empate_na_nota_desempata_pelo_nome_da_categoria():
    df = pd.DataFrame({
        "categoria": ["b", "a", "c"],
        "nota_media": [4.0, 4.0, 3.0],
        "posicao_pior": [2, 2, 1],
    })
    fig = painel.grafico_nota_categoria(df)
    assert list(fig.data[0].y) == ["c", "a", "b"]


def test_vendedores_tem_um_ponto_por_posicao_e_linha_tracejada_em_80():
    df = pd.DataFrame({
        "posicao": [3, 1, 2, 4],
        "pct_acumulado": [90.0, 50.0, 70.0, 100.0],
    })
    fig = painel.grafico_vendedores(df)
    assert _pontos(fig) == 4
    assert list(fig.data[0].x) == [1, 2, 3, 4]
    assert [(s.y0, s.line.dash) for s in fig.layout.shapes] == [(80, "dash")]


def test_cada_grafico_usa_uma_cor_so():
    meses = _vendas_mensais("2017-01-01", "2017-03-01", como_data=False)
    figuras = [
        painel.grafico_faturamento(meses),
        painel.grafico_categorias(pd.DataFrame({"categoria": ["a", "b"], "receita": [1.0, 2.0]})),
        painel.grafico_pagamento(pd.DataFrame({"tipo": ["a", "b"], "pct_valor": [1.0, 2.0]})),
        painel.grafico_ticket_uf(pd.DataFrame({"uf": ["a", "b"], "ticket_medio": [1.0, 2.0]})),
        painel.grafico_clientes_uf(pd.DataFrame({"uf": ["a", "b"], "clientes": [1, 2]})),
        painel.grafico_nota_categoria(pd.DataFrame(
            {"categoria": ["a", "b"], "nota_media": [1.0, 2.0], "posicao_pior": [1, 2]})),
        painel.grafico_vendedores(pd.DataFrame({"posicao": [1, 2], "pct_acumulado": [1.0, 2.0]})),
    ]
    assert [len(f.data) for f in figuras] == [1] * 7


def test_titulos_comecam_com_o_numero_do_mart():
    meses = _vendas_mensais("2017-01-01", "2017-03-01", como_data=False)
    pares = [
        (painel.grafico_faturamento(meses), "01 ·"),
        (painel.grafico_categorias(pd.DataFrame({"categoria": ["a"], "receita": [1.0]})), "02 ·"),
        (painel.grafico_nota_categoria(pd.DataFrame(
            {"categoria": ["a"], "nota_media": [1.0], "posicao_pior": [1]})), "04 ·"),
        (painel.grafico_ticket_uf(pd.DataFrame({"uf": ["a"], "ticket_medio": [1.0]})), "06 ·"),
        (painel.grafico_pagamento(pd.DataFrame({"tipo": ["a"], "pct_valor": [1.0]})), "07 ·"),
        (painel.grafico_vendedores(pd.DataFrame({"posicao": [1], "pct_acumulado": [1.0]})), "09 ·"),
        (painel.grafico_clientes_uf(pd.DataFrame({"uf": ["a"], "clientes": [1]})), "12 ·"),
    ]
    assert [fig.layout.title.text.startswith(prefixo) for fig, prefixo in pares] == [True] * 7


def test_graficos_usam_virgula_decimal_e_ponto_de_milhar():
    df = pd.DataFrame({"categoria": ["a"], "receita": [1.0]})
    assert painel.grafico_categorias(df).layout.separators == ",."


# ------------------------------------------------------------------ leitura dos marts

def _banco_de_marts(tmp_path, monkeypatch):
    caminho = tmp_path / "olist.duckdb"
    monkeypatch.setattr(painel, "CAMINHO_BANCO", caminho)
    con = duckdb.connect(str(caminho))
    con.execute("CREATE SCHEMA marts")
    con.execute("CREATE TABLE marts.alfa AS SELECT * FROM (VALUES (1, 'x'), (2, 'y')) AS t(n, s)")
    con.execute("CREATE TABLE marts.beta AS SELECT 7.5::DOUBLE AS v")
    con.close()
    return caminho


def test_ler_devolve_um_dataframe_por_mart_com_todas_as_linhas(tmp_path, monkeypatch):
    _banco_de_marts(tmp_path, monkeypatch)
    dados = painel.ler(["alfa", "beta"])
    assert sorted(dados) == ["alfa", "beta"]
    assert list(dados["alfa"]["n"]) == [1, 2]
    assert list(dados["alfa"]["s"]) == ["x", "y"]
    assert list(dados["beta"]["v"]) == [7.5]


def test_ler_lista_todos_os_marts_que_faltam(tmp_path, monkeypatch):
    _banco_de_marts(tmp_path, monkeypatch)
    with pytest.raises(painel.MartsAusentes) as erro:
        painel.ler(["alfa", "gama", "delta"])
    assert erro.value.nomes == ["gama", "delta"]


def test_ler_sem_o_schema_marts_conta_todos_como_ausentes(tmp_path, monkeypatch):
    caminho = tmp_path / "olist.duckdb"
    monkeypatch.setattr(painel, "CAMINHO_BANCO", caminho)
    con = duckdb.connect(str(caminho))
    con.execute("CREATE TABLE t AS SELECT 1 AS x")
    con.close()
    with pytest.raises(painel.MartsAusentes) as erro:
        painel.ler(["alfa", "beta"])
    assert erro.value.nomes == ["alfa", "beta"]


def test_ler_sem_o_arquivo_do_banco_avisa_e_nao_cria_arquivo(tmp_path, monkeypatch):
    caminho = tmp_path / "olist.duckdb"
    monkeypatch.setattr(painel, "CAMINHO_BANCO", caminho)
    with pytest.raises(painel.BancoAusente) as erro:
        painel.ler(["alfa"])
    assert str(caminho) in str(erro.value)
    assert not caminho.exists()


def test_ler_fecha_a_conexao_e_o_pipeline_consegue_gravar_depois(tmp_path, monkeypatch):
    caminho = _banco_de_marts(tmp_path, monkeypatch)
    painel.ler(["alfa"])
    con = duckdb.connect(str(caminho))
    con.execute("CREATE TABLE marts.gravada AS SELECT 1 AS x")
    achadas = con.execute("SELECT count(*) FROM marts.gravada").fetchall()
    con.close()
    assert achadas == [(1,)]
