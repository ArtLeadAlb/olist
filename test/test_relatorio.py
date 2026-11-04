"""Testes de relatorio.py sobre marts inventados, gravados num banco de tmp_path."""

import io
import re
import sys
from datetime import datetime

import duckdb
import pytest

import painel
from pipeline import relatorio


class _Relogio:
    """Troca o datetime de relatorio.py para o rodapé ser conhecido."""
    agora = datetime(2026, 10, 25, 14, 3)

    @classmethod
    def now(cls):
        return cls.agora


def _semear(tmp_path, monkeypatch, vendedores=5, omitir=()):
    """Cria os dez marts do relatório com valores inventados e aponta o código para eles."""
    caminho = tmp_path / "olist.duckdb"
    monkeypatch.setattr(painel, "CAMINHO_BANCO", caminho)
    monkeypatch.setattr(relatorio, "ARQUIVO", tmp_path / "relatorio.html")
    monkeypatch.setattr(relatorio, "datetime", _Relogio)
    comandos = {
        "kpis": (
            "SELECT 150.5::DOUBLE AS ticket_medio, 2.0::DOUBLE AS ticket_mediana, "
            "10.0::DOUBLE AS pct_frete, 1.25::DOUBLE AS pct_cancelados, "
            "9.5::DOUBLE AS dias_entrega, 8.0::DOUBLE AS dias_entrega_mediana, "
            "4.25::DOUBLE AS nota_media"
        ),
        "recompra": (
            "SELECT * FROM (VALUES (1, 900, 90.0::DOUBLE), (2, 100, 10.0::DOUBLE)) "
            "AS t(pedidos_por_cliente, clientes, pct_clientes)"
        ),
        "entrega_no_prazo": (
            "SELECT 100 AS entregues, 80 AS no_prazo, 20 AS atrasados, "
            "80.5::DOUBLE AS pct_no_prazo"
        ),
        "vendas_mensais": (
            "SELECT CAST(d AS DATE) AS mes, 10 AS pedidos, 1000.5::DOUBLE AS receita "
            "FROM generate_series(DATE '2016-12-01', DATE '2018-10-01', INTERVAL 1 MONTH) AS t(d)"
        ),
        "top_categorias": (
            "SELECT * FROM (VALUES ('beleza', 5, 6, 300.0::DOUBLE), ('moda', 3, 4, 100.0::DOUBLE)) "
            "AS t(categoria, pedidos, itens, receita)"
        ),
        "mix_pagamento": (
            "SELECT * FROM (VALUES ('cartao', 8, 7, 800.0::DOUBLE, 80.0::DOUBLE), "
            "('boleto', 2, 2, 200.0::DOUBLE, 20.0::DOUBLE)) "
            "AS t(tipo, pagamentos, pedidos, valor, pct_valor)"
        ),
        "ticket_medio_por_estado": (
            "SELECT * FROM (VALUES ('SP', 10, 90.0::DOUBLE), ('PB', 2, 200.0::DOUBLE)) "
            "AS t(uf, pedidos, ticket_medio)"
        ),
        "clientes_por_uf": (
            "SELECT * FROM (VALUES ('SP', 500), ('PB', 5)) AS t(uf, clientes)"
        ),
        "nota_por_categoria": (
            "SELECT * FROM (VALUES ('beleza', 100, 4.5::DOUBLE, 2), ('moda', 100, 3.5::DOUBLE, 1)) "
            "AS t(categoria, pedidos_avaliados, nota_media, posicao_pior)"
        ),
        "vendedores_pareto": (
            f"SELECT 'v' || i AS vendedor_id, 'SP' AS uf, 10.0::DOUBLE AS receita, "
            f"i + 1 AS posicao, round(100.0 * (i + 1) / {vendedores}, 2)::DOUBLE AS pct_acumulado "
            f"FROM range({vendedores}) AS t(i)"
        ),
    }
    con = duckdb.connect(str(caminho))
    con.execute("CREATE SCHEMA marts")
    for nome, consulta in comandos.items():
        if nome not in omitir:
            con.execute(f"CREATE TABLE marts.{nome} AS {consulta}")
    con.close()


def _capturar(monkeypatch):
    saida = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    erro = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", saida)
    monkeypatch.setattr(sys, "stderr", erro)

    def ler():
        saida.flush()
        erro.flush()
        return (saida.buffer.getvalue().decode("utf-8"),
                erro.buffer.getvalue().decode("utf-8"))

    return ler


def _gerar(tmp_path, monkeypatch, **opcoes):
    _semear(tmp_path, monkeypatch, **opcoes)
    ler = _capturar(monkeypatch)
    relatorio.main()
    return (tmp_path / "relatorio.html").read_text(encoding="utf-8"), ler()[0]


def _sem_rodape(html):
    return re.sub(r"<footer>.*?</footer>", "<footer></footer>", html)


def test_gera_o_arquivo_dentro_de_tmp_path_e_imprime_caminho_e_tamanho(tmp_path, monkeypatch):
    _, saida = _gerar(tmp_path, monkeypatch)
    arquivo = tmp_path / "relatorio.html"
    assert arquivo.exists()
    assert str(arquivo) in saida
    assert "KB" in saida


def test_os_sete_cartoes_mostram_os_valores_da_entrada_na_ordem(tmp_path, monkeypatch):
    html, _ = _gerar(tmp_path, monkeypatch)
    valores = re.findall(r'class="valor">([^<]+)<', html)
    assert valores == [
        "R$ 150,50",  # ticket médio
        "1,25%",      # cancelados, 2 casas
        "10,0%",      # peso do frete, 1 casa
        "10,00%",     # recompra: 100 menos os 90,0 de quem comprou uma vez
        "80,5%",      # no prazo
        "9,5",        # dias até entregar
        "4,25",       # nota média
    ]


def test_as_quatro_faixas_aparecem_na_ordem_do_painel(tmp_path, monkeypatch):
    html, _ = _gerar(tmp_path, monkeypatch)
    faixas = re.findall(r'<section class="(\w+)"', html)
    assert faixas == ["cartoes", "largo", "tres", "tres"]


def test_cada_grafico_tem_div_id_fixo_na_ordem(tmp_path, monkeypatch):
    html, _ = _gerar(tmp_path, monkeypatch)
    ids = re.findall(r'<div id="(g\d\d)"', html)
    assert ids == [f"g0{i}" for i in range(1, 8)]


def test_a_biblioteca_do_plotly_vem_do_cdn_uma_vez_so(tmp_path, monkeypatch):
    html, _ = _gerar(tmp_path, monkeypatch)
    assert html.count("cdn.plot.ly") == 1
    assert html.index("cdn.plot.ly") < html.index('id="g01"') + len('id="g01"') + 400


def test_rodape_traz_a_data_e_a_hora_da_geracao(tmp_path, monkeypatch):
    html, _ = _gerar(tmp_path, monkeypatch)
    assert "<footer>Dados de 25/10/2026 14:03</footer>" in html


def test_rodar_duas_vezes_muda_so_o_rodape(tmp_path, monkeypatch):
    primeiro, _ = _gerar(tmp_path, monkeypatch)
    monkeypatch.setattr(_Relogio, "agora", datetime(2026, 10, 26, 9, 30))
    ler = _capturar(monkeypatch)
    relatorio.main()
    ler()
    segundo = (tmp_path / "relatorio.html").read_text(encoding="utf-8")
    assert primeiro != segundo
    assert "Dados de 26/10/2026 09:30" in segundo
    assert _sem_rodape(primeiro) == _sem_rodape(segundo)


def test_faturamento_mostra_o_periodo_padrao_no_titulo_e_vinte_meses(tmp_path, monkeypatch):
    _semear(tmp_path, monkeypatch)
    dados = painel.ler(list(relatorio.MARTS))
    faturamento = relatorio._figuras(dados)[0]
    assert faturamento.layout.title.text == "01 · Faturamento mensal · jan/2017 a ago/2018"
    assert len(faturamento.data[0].x) == 20


def test_so_o_faturamento_e_recortado_os_outros_graficos_mostram_tudo(tmp_path, monkeypatch):
    _semear(tmp_path, monkeypatch, vendedores=7)
    dados = painel.ler(list(relatorio.MARTS))
    figuras = relatorio._figuras(dados)
    assert len(figuras) == 7
    assert len(figuras[1].data[0].y) == 2   # categorias
    assert len(figuras[6].data[0].x) == 7   # vendedores


def test_arquivo_com_tres_mil_vendedores_fica_abaixo_de_200_kb(tmp_path, monkeypatch):
    # o gráfico de vendedores é o maior: um ponto por vendedor
    _gerar(tmp_path, monkeypatch, vendedores=3000)
    tamanho = (tmp_path / "relatorio.html").stat().st_size
    assert tamanho < 200 * 1024


def test_banco_ausente_encerra_com_o_comando_para_gerar_os_marts(tmp_path, monkeypatch):
    monkeypatch.setattr(painel, "CAMINHO_BANCO", tmp_path / "olist.duckdb")
    monkeypatch.setattr(relatorio, "ARQUIVO", tmp_path / "relatorio.html")
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        relatorio.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "uv run python -m pipeline.marts" in erro
    assert not (tmp_path / "relatorio.html").exists()


def test_mart_ausente_lista_quais_e_nao_escreve_o_arquivo(tmp_path, monkeypatch):
    _semear(tmp_path, monkeypatch, omitir=("kpis", "recompra"))
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        relatorio.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "kpis" in erro and "recompra" in erro
    assert not (tmp_path / "relatorio.html").exists()
