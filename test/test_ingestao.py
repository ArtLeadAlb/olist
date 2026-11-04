"""Testes de pipeline/ingestao.py com CSVs pequenos escritos pelo próprio teste."""

import gzip
import io
import sys

import duckdb
import pytest

from pipeline import db, ingestao

ARQUIVOS = list(ingestao.ARQUIVO_PARA_TABELA)
PEDIDOS = "olist_orders_dataset.csv.gz"
CLIENTES = "olist_customers_dataset.csv.gz"
AVALIACOES = "olist_order_reviews_dataset.csv.gz"
GEOLOCALIZACAO = "olist_geolocation_dataset.csv.gz"


def _preparar(tmp_path, monkeypatch, conteudos=None, sem=()):
    """Escreve os nove .csv.gz em tmp_path/raw e aponta o código para eles."""
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(ingestao, "PASTA_RAW", raw)
    monkeypatch.setattr(db, "_RAIZ", tmp_path)
    for arquivo in ARQUIVOS:
        if arquivo in sem:
            continue
        linhas = (conteudos or {}).get(arquivo, ["id", "1"])
        with gzip.open(raw / arquivo, "wt", encoding="utf-8", newline="") as f:
            f.write("\n".join(linhas) + "\n")
    return raw


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


def test_csv_vira_tabela_com_as_mesmas_linhas_inclusive_a_repetida(tmp_path, monkeypatch):
    # pedido "a" aparece duas vezes: a ingestão não deduplica
    _preparar(tmp_path, monkeypatch, {
        PEDIDOS: ["order_id,order_status", "a,delivered", "b,canceled", "a,delivered"],
    })
    _capturar(monkeypatch)
    ingestao.main()
    assert _consultar(tmp_path, "SELECT count(*) FROM raw.pedidos") == [(3,)]
    assert _consultar(tmp_path, "SELECT order_id FROM raw.pedidos ORDER BY order_id") == [
        ("a",), ("a",), ("b",),
    ]


def test_as_nove_tabelas_nascem_no_schema_raw_com_nomes_em_portugues(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    _capturar(monkeypatch)
    ingestao.main()
    tabelas = _consultar(
        tmp_path,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'",
    )
    assert {t[0] for t in tabelas} == {
        "pedidos", "itens_pedido", "pagamentos", "avaliacoes", "clientes",
        "vendedores", "produtos", "traducao_categorias", "geolocalizacao",
    }


def test_saida_tem_uma_linha_por_tabela_o_total_e_milhar_com_ponto(tmp_path, monkeypatch):
    # 3 pedidos + 1.000 pontos de geolocalização + 1 linha em cada uma das outras sete
    _preparar(tmp_path, monkeypatch, {
        PEDIDOS: ["order_id", "a", "b", "c"],
        GEOLOCALIZACAO: ["id"] + [str(i) for i in range(1000)],
    })
    ler = _capturar(monkeypatch)
    ingestao.main()
    saida, _ = ler()
    assert len(saida.splitlines()) == 10
    assert "raw.pedidos: 3 linhas" in saida
    assert "raw.geolocalizacao: 1.000 linhas" in saida
    assert "Total: 1.010 registros" in saida


def test_todas_as_colunas_entram_como_varchar(tmp_path, monkeypatch):
    # valores que uma inferência transformaria em número, data e booleano
    _preparar(tmp_path, monkeypatch, {
        PEDIDOS: ["order_id,quantidade,data,ativo", "1,10,2017-10-02 10:56:33,true"],
    })
    _capturar(monkeypatch)
    ingestao.main()
    tipos = _consultar(
        tmp_path,
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'pedidos'",
    )
    assert tipos == [("VARCHAR",)] * 4


def test_nomes_de_coluna_ficam_como_vieram(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {PEDIDOS: ["Order_ID,order_status", "a,x"]})
    _capturar(monkeypatch)
    ingestao.main()
    colunas = _consultar(
        tmp_path,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'pedidos' ORDER BY ordinal_position",
    )
    assert colunas == [("Order_ID",), ("order_status",)]


def test_zero_a_esquerda_do_cep_sobrevive(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {
        CLIENTES: ["customer_id,customer_zip_code_prefix", "c1,01151"],
    })
    _capturar(monkeypatch)
    ingestao.main()
    assert _consultar(tmp_path, "SELECT customer_zip_code_prefix FROM raw.clientes") == [("01151",)]


def test_campo_vazio_vira_nulo_e_nao_string_vazia(tmp_path, monkeypatch):
    # pedido "a" sem status
    _preparar(tmp_path, monkeypatch, {PEDIDOS: ["order_id,order_status", "a,"]})
    _capturar(monkeypatch)
    ingestao.main()
    nulos = _consultar(tmp_path, "SELECT count(*) FROM raw.pedidos WHERE order_status IS NULL")
    vazios = _consultar(tmp_path, "SELECT count(*) FROM raw.pedidos WHERE order_status = ''")
    assert (nulos, vazios) == ([(1,)], [(0,)])


def test_texto_na_continua_texto_e_nao_vira_nulo(tmp_path, monkeypatch):
    # "NA" escrito no arquivo é dado, não campo vazio
    _preparar(tmp_path, monkeypatch, {PEDIDOS: ["order_id,order_status", "a,NA"]})
    _capturar(monkeypatch)
    ingestao.main()
    assert _consultar(tmp_path, "SELECT order_status FROM raw.pedidos") == [("NA",)]


def test_acento_sobrevive_porque_o_encoding_e_utf8(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {
        CLIENTES: ["customer_id,customer_city", "c1,São Paulo"],
    })
    _capturar(monkeypatch)
    ingestao.main()
    assert _consultar(tmp_path, "SELECT customer_city FROM raw.clientes") == [("São Paulo",)]


def test_campo_entre_aspas_com_quebra_de_linha_continua_um_campo(tmp_path, monkeypatch):
    # comentário de avaliação com vírgula e quebra de linha dentro das aspas
    comentario = 'linha um\nlinha dois, com vírgula'
    _preparar(tmp_path, monkeypatch, {
        AVALIACOES: ["review_id,review_comment_message", f'r1,"{comentario}"'],
    })
    _capturar(monkeypatch)
    ingestao.main()
    assert _consultar(tmp_path, "SELECT count(*) FROM raw.avaliacoes") == [(1,)]
    assert _consultar(tmp_path, "SELECT review_comment_message FROM raw.avaliacoes") == [(comentario,)]


def test_rodar_duas_vezes_da_a_mesma_saida_e_a_mesma_contagem(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {PEDIDOS: ["order_id", "a", "b"]})
    ler = _capturar(monkeypatch)
    ingestao.main()
    primeira, _ = ler()
    ler = _capturar(monkeypatch)
    ingestao.main()
    segunda, _ = ler()
    assert primeira == segunda
    assert _consultar(tmp_path, "SELECT count(*) FROM raw.pedidos") == [(2,)]


def test_arquivo_faltando_encerra_antes_de_abrir_o_banco(tmp_path, monkeypatch):
    raw = _preparar(tmp_path, monkeypatch, sem=(PEDIDOS, CLIENTES))
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        ingestao.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert PEDIDOS in erro and CLIENTES in erro
    assert str(raw) in erro
    assert not (tmp_path / "olist.duckdb").exists()
