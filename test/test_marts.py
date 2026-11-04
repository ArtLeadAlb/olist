"""Testes de pipeline/marts.py e de sql/marts/01 e 03, sobre tabelas refined inventadas."""

import datetime as dt
import decimal
import io
import sys
from pathlib import Path

import duckdb
import pytest

from pipeline import db, marts

SQL_REAL = Path(__file__).resolve().parent.parent / "sql" / "marts"

PEDIDOS_COLUNAS = (
    "pedido_id VARCHAR, status VARCHAR, data_compra TIMESTAMP, "
    "data_entrega TIMESTAMP, data_entrega_prevista DATE"
)


def _preparar(tmp_path, monkeypatch, arquivos=None, omitir=(), pedidos=(), itens=()):
    """Banco em tmp_path com as oito tabelas de refined e a pasta de marts com os arquivos dados."""
    monkeypatch.setattr(db, "_RAIZ", tmp_path)
    pasta = tmp_path / "sql" / "marts"
    monkeypatch.setattr(marts, "PASTA_MARTS", pasta)
    con = duckdb.connect(str(tmp_path / "olist.duckdb"))
    con.execute("CREATE SCHEMA refined")
    for tabela in marts.TABELAS_ENTRADA:
        if tabela in omitir:
            continue
        if tabela == "pedidos":
            con.execute(f"CREATE TABLE refined.pedidos ({PEDIDOS_COLUNAS})")
            if pedidos:  # executemany do DuckDB não aceita lista vazia
                con.executemany("INSERT INTO refined.pedidos VALUES (?, ?, ?, ?, ?)", list(pedidos))
        elif tabela == "itens_pedido":
            con.execute("CREATE TABLE refined.itens_pedido (pedido_id VARCHAR, preco DECIMAL(10,2))")
            if itens:
                con.executemany("INSERT INTO refined.itens_pedido VALUES (?, ?)", list(itens))
        else:
            con.execute(f"CREATE TABLE refined.{tabela} (x INTEGER)")
    con.close()
    if arquivos is not None:
        pasta.mkdir(parents=True)
        for nome, texto in arquivos.items():
            _escrever(pasta, nome, texto)
    return pasta


def _escrever(pasta, nome, texto):
    (pasta / nome).write_text(texto, encoding="utf-8")


def _copiar_real(pasta, nome):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_bytes((SQL_REAL / nome).read_bytes())


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


def _consultar(tmp_path, sql):
    con = duckdb.connect(str(tmp_path / "olist.duckdb"), read_only=True)
    linhas = con.execute(sql).fetchall()
    con.close()
    return linhas


def _tabelas_de_marts(tmp_path):
    achadas = _consultar(
        tmp_path,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'",
    )
    return sorted(t[0] for t in achadas)


def _schema_marts_existe(tmp_path):
    achadas = _consultar(
        tmp_path,
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'marts'",
    )
    return achadas == [(1,)]


# ------------------------------------------------------------------ um arquivo, uma tabela

def test_arquivo_sem_o_prefixo_numerico_da_nome_a_tabela(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x"})
    ler = _capturar(monkeypatch)
    marts.main()
    saida, _ = ler()
    assert _consultar(tmp_path, "SELECT x FROM marts.teste") == [(1,)]
    assert "✓ marts.teste" in saida
    assert "1 linhas" in saida
    assert "1 marts, 1 linhas no total" in saida


def test_mart_le_do_refined_sem_alterar_o_refined(tmp_path, monkeypatch):
    pedidos = [("a", "delivered", None, None, None), ("b", "canceled", None, None, None)]
    _preparar(tmp_path, monkeypatch, {"01_contagem.sql": "SELECT count(*) AS n FROM refined.pedidos"},
              pedidos=pedidos)
    _capturar(monkeypatch)
    marts.main()
    assert _consultar(tmp_path, "SELECT n FROM marts.contagem") == [(2,)]
    assert _consultar(tmp_path, "SELECT count(*) FROM refined.pedidos") == [(2,)]


def test_arquivos_rodam_em_ordem_alfabetica(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {
        "02_segundo.sql": "SELECT 2 AS x",
        "01_primeiro.sql": "SELECT 1 AS x",
    })
    ler = _capturar(monkeypatch)
    marts.main()
    saida, _ = ler()
    assert saida.index("marts.primeiro") < saida.index("marts.segundo")


def test_ponto_e_virgula_e_espacos_do_final_sao_tirados(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x ;  \n\n"})
    _capturar(monkeypatch)
    marts.main()
    assert _consultar(tmp_path, "SELECT x FROM marts.teste") == [(1,)]


def test_comentarios_e_with_no_comeco_do_arquivo_funcionam(tmp_path, monkeypatch):
    sql = "-- um comentário com acento: mês\nWITH base AS (SELECT 7 AS x)\nSELECT x FROM base"
    _preparar(tmp_path, monkeypatch, {"00_teste.sql": sql})
    _capturar(monkeypatch)
    marts.main()
    assert _consultar(tmp_path, "SELECT x FROM marts.teste") == [(7,)]


def test_bom_no_comeco_do_arquivo_nao_quebra_a_sql(tmp_path, monkeypatch):
    # editores do Windows podem gravar o arquivo com BOM
    _preparar(tmp_path, monkeypatch, {"00_teste.sql": "\ufeffSELECT 1 AS x"})
    _capturar(monkeypatch)
    marts.main()
    assert _consultar(tmp_path, "SELECT x FROM marts.teste") == [(1,)]


def test_rodar_duas_vezes_da_a_mesma_saida(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x"})
    ler = _capturar(monkeypatch)
    marts.main()
    primeira, _ = ler()
    ler = _capturar(monkeypatch)
    marts.main()
    segunda, _ = ler()
    assert primeira == segunda
    assert _tabelas_de_marts(tmp_path) == ["teste"]


def test_apagar_o_arquivo_faz_o_mart_sumir_na_execucao_seguinte(tmp_path, monkeypatch):
    pasta = _preparar(tmp_path, monkeypatch, {
        "00_teste.sql": "SELECT 1 AS x",
        "01_fica.sql": "SELECT 2 AS y",
    })
    _capturar(monkeypatch)
    marts.main()
    antes = _tabelas_de_marts(tmp_path)
    (pasta / "00_teste.sql").unlink()
    _capturar(monkeypatch)
    marts.main()
    assert antes == ["fica", "teste"]
    assert _tabelas_de_marts(tmp_path) == ["fica"]


# ------------------------------------------------------------------ validações antes de executar

def test_arquivo_sem_prefixo_para_antes_de_executar_qualquer_sql(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {
        "00_ok.sql": "SELECT 1 AS x",
        "teste.sql": "SELECT 1 AS x",
    })
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        marts.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "teste.sql" in erro
    assert not _schema_marts_existe(tmp_path)


def test_dois_arquivos_com_o_mesmo_nome_de_tabela_param_antes_de_executar(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {
        "01_vendas.sql": "SELECT 1 AS x",
        "02_vendas.sql": "SELECT 2 AS x",
    })
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        marts.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "01_vendas.sql" in erro and "02_vendas.sql" in erro
    assert not _schema_marts_existe(tmp_path)


def test_nomes_que_so_diferem_na_caixa_contam_como_a_mesma_tabela(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {
        "01_vendas.sql": "SELECT 1 AS x",
        "02_Vendas.sql": "SELECT 2 AS x",
    })
    _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        marts.main()
    assert encerrou.value.code == 1


def test_pasta_sem_arquivo_encerra_avisando(tmp_path, monkeypatch):
    pasta = _preparar(tmp_path, monkeypatch, {})
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        marts.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert str(pasta) in erro


def test_pasta_que_nao_existe_encerra_do_mesmo_jeito(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        marts.main()
    assert encerrou.value.code == 1


def test_tabela_faltando_em_refined_lista_e_manda_rodar_a_transformacao(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x"},
              omitir=("avaliacoes", "vendedores"))
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        marts.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "avaliacoes" in erro and "vendedores" in erro
    assert "pipeline.transformacao" in erro
    assert not _schema_marts_existe(tmp_path)


# ------------------------------------------------------------------ falha no meio: tudo volta

def test_erro_de_sintaxe_para_tudo_e_o_schema_marts_fica_como_estava(tmp_path, monkeypatch):
    pasta = _preparar(tmp_path, monkeypatch, {
        "00_teste.sql": "SELECT 1 AS x",
        "01_outro.sql": "SELECT 2 AS y",
    })
    _capturar(monkeypatch)
    marts.main()
    # segunda execução: o primeiro mart muda de valor, o segundo ganha erro de sintaxe
    _escrever(pasta, "00_teste.sql", "SELECT 10 AS x")
    _escrever(pasta, "01_outro.sql", "SELEC 2 AS y")
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        marts.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "01_outro.sql" in erro
    assert _consultar(tmp_path, "SELECT x FROM marts.teste") == [(1,)]
    assert _consultar(tmp_path, "SELECT y FROM marts.outro") == [(2,)]


def test_falha_na_primeira_execucao_nao_deixa_schema_pela_metade(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {
        "00_ok.sql": "SELECT 1 AS x",
        "01_ruim.sql": "SELEC 2 AS y",
        "02_depois.sql": "SELECT 3 AS z",
    })
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        marts.main()
    saida, erro = ler()
    assert encerrou.value.code == 1
    assert "01_ruim.sql" in erro
    assert "✓" not in saida
    assert not _schema_marts_existe(tmp_path)


def test_mart_vazio_encerra_e_o_schema_marts_fica_como_estava(tmp_path, monkeypatch):
    pasta = _preparar(tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x"})
    _capturar(monkeypatch)
    marts.main()
    # segunda execução: um mart novo que não devolve linha nenhuma
    _escrever(pasta, "01_vazio.sql", "SELECT 1 AS x WHERE false")
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        marts.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "vazio" in erro and "zero linhas" in erro
    assert _tabelas_de_marts(tmp_path) == ["teste"]


# ------------------------------------------------------------------ sql/marts/01_vendas_mensais.sql

def _vendas(tmp_path, monkeypatch, pedidos, itens):
    pasta = _preparar(tmp_path, monkeypatch, pedidos=pedidos, itens=itens)
    _copiar_real(pasta, "01_vendas_mensais.sql")
    _capturar(monkeypatch)
    marts.main()
    return _consultar(
        tmp_path, "SELECT mes, pedidos, receita FROM marts.vendas_mensais ORDER BY mes"
    )


def test_pedido_com_dois_itens_conta_uma_vez_e_soma_os_dois(tmp_path, monkeypatch):
    # um pedido entregue, com itens de 10,00 e 20,00
    pedidos = [("p1", "delivered", dt.datetime(2017, 1, 10, 10, 0), None, None)]
    itens = [("p1", "10.00"), ("p1", "20.00")]
    linhas = _vendas(tmp_path, monkeypatch, pedidos, itens)
    assert linhas == [(dt.date(2017, 1, 1), 1, decimal.Decimal("30.00"))]


def test_cancelado_fica_fora_da_receita(tmp_path, monkeypatch):
    pedidos = [
        ("p1", "delivered", dt.datetime(2017, 1, 10, 10, 0), None, None),
        ("p2", "canceled", dt.datetime(2017, 1, 11, 10, 0), None, None),  # cancelado: fora
    ]
    itens = [("p1", "10.00"), ("p2", "99.00")]
    linhas = _vendas(tmp_path, monkeypatch, pedidos, itens)
    assert linhas == [(dt.date(2017, 1, 1), 1, decimal.Decimal("10.00"))]


def test_indisponivel_fica_fora_da_receita(tmp_path, monkeypatch):
    pedidos = [
        ("p1", "delivered", dt.datetime(2017, 1, 10, 10, 0), None, None),
        ("p2", "unavailable", dt.datetime(2017, 1, 11, 10, 0), None, None),  # indisponível: fora
    ]
    itens = [("p1", "10.00"), ("p2", "99.00")]
    linhas = _vendas(tmp_path, monkeypatch, pedidos, itens)
    assert linhas == [(dt.date(2017, 1, 1), 1, decimal.Decimal("10.00"))]


def test_pedido_do_ultimo_minuto_do_mes_fica_no_proprio_mes(tmp_path, monkeypatch):
    pedidos = [
        ("p1", "delivered", dt.datetime(2017, 1, 31, 23, 59, 59), None, None),
        ("p2", "delivered", dt.datetime(2017, 2, 1, 0, 0, 0), None, None),
    ]
    itens = [("p1", "5.00"), ("p2", "7.00")]
    linhas = _vendas(tmp_path, monkeypatch, pedidos, itens)
    assert linhas == [
        (dt.date(2017, 1, 1), 1, decimal.Decimal("5.00")),
        (dt.date(2017, 2, 1), 1, decimal.Decimal("7.00")),
    ]


def test_pedido_sem_item_nao_entra_no_faturamento(tmp_path, monkeypatch):
    pedidos = [
        ("p1", "delivered", dt.datetime(2017, 1, 10, 10, 0), None, None),
        ("p2", "delivered", dt.datetime(2017, 1, 12, 10, 0), None, None),  # sem item nenhum
    ]
    itens = [("p1", "10.00")]
    linhas = _vendas(tmp_path, monkeypatch, pedidos, itens)
    assert linhas == [(dt.date(2017, 1, 1), 1, decimal.Decimal("10.00"))]


# ------------------------------------------------------------------ sql/marts/03_entrega_no_prazo.sql

def _prazo(tmp_path, monkeypatch, pedidos):
    pasta = _preparar(tmp_path, monkeypatch, pedidos=pedidos)
    _copiar_real(pasta, "03_entrega_no_prazo.sql")
    _capturar(monkeypatch)
    marts.main()
    linhas = _consultar(
        tmp_path, "SELECT entregues, no_prazo, atrasados, pct_no_prazo FROM marts.entrega_no_prazo"
    )
    assert len(linhas) == 1
    entregues, no_prazo, atrasados, pct = linhas[0]
    return entregues, no_prazo, atrasados, float(pct)


def test_entrega_no_dia_previsto_a_tarde_esta_no_prazo(tmp_path, monkeypatch):
    # entregue às 15h do próprio dia previsto
    pedidos = [("d1", "delivered", None, dt.datetime(2017, 3, 10, 15, 0), dt.date(2017, 3, 10))]
    assert _prazo(tmp_path, monkeypatch, pedidos) == (1, 1, 0, 100.0)


def test_entrega_antes_do_dia_previsto_esta_no_prazo(tmp_path, monkeypatch):
    pedidos = [("d1", "delivered", None, dt.datetime(2017, 3, 9, 8, 0), dt.date(2017, 3, 10))]
    assert _prazo(tmp_path, monkeypatch, pedidos) == (1, 1, 0, 100.0)


def test_entrega_no_dia_seguinte_esta_atrasada(tmp_path, monkeypatch):
    # um minuto depois da meia-noite do dia seguinte ao previsto
    pedidos = [("d1", "delivered", None, dt.datetime(2017, 3, 11, 0, 1), dt.date(2017, 3, 10))]
    assert _prazo(tmp_path, monkeypatch, pedidos) == (1, 0, 1, 0.0)


def test_pedido_delivered_sem_data_de_entrega_fica_fora(tmp_path, monkeypatch):
    pedidos = [
        ("d1", "delivered", None, dt.datetime(2017, 3, 10, 15, 0), dt.date(2017, 3, 10)),
        ("d2", "delivered", None, None, dt.date(2017, 3, 10)),  # data de entrega nula
    ]
    assert _prazo(tmp_path, monkeypatch, pedidos) == (1, 1, 0, 100.0)


def test_pedido_que_nao_esta_delivered_fica_fora(tmp_path, monkeypatch):
    pedidos = [
        ("d1", "delivered", None, dt.datetime(2017, 3, 10, 15, 0), dt.date(2017, 3, 10)),
        ("d2", "canceled", None, dt.datetime(2017, 3, 5, 9, 0), dt.date(2017, 3, 10)),
    ]
    assert _prazo(tmp_path, monkeypatch, pedidos) == (1, 1, 0, 100.0)


def test_percentual_no_prazo_e_no_prazo_dividido_por_entregues(tmp_path, monkeypatch):
    pedidos = [
        ("d1", "delivered", None, dt.datetime(2017, 3, 10, 15, 0), dt.date(2017, 3, 10)),  # no prazo
        ("d2", "delivered", None, dt.datetime(2017, 3, 9, 8, 0), dt.date(2017, 3, 10)),    # adiantado
        ("d3", "delivered", None, dt.datetime(2017, 3, 11, 0, 1), dt.date(2017, 3, 10)),   # atrasado
    ]
    esperado = round(100 * 2 / 3, 1)
    assert _prazo(tmp_path, monkeypatch, pedidos) == (3, 2, 1, esperado)
