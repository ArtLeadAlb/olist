"""Testes de pipeline/transformacao.py sobre tabelas raw inventadas pelo teste."""

import datetime as dt
import decimal
import io
import sys

import duckdb
import pytest

from pipeline import db, transformacao

# Valor válido para cada tipo, para cada linha inventada começar sem nulo.
PADRAO = {
    transformacao.TXT: "x",
    transformacao.TS: "2017-01-01 10:00:00",
    transformacao.DATA: "2017-01-01 00:00:00",
    transformacao.DEC: "1.00",
    transformacao.INT: "1",
}

OITO = [
    "pedidos", "itens_pedido", "pagamentos", "clientes",
    "vendedores", "produtos", "traducao_categorias", "avaliacoes",
]


def _linha(tabela, **sobrescritas):
    """Linha de raw com valores válidos; sobrescritas usam os nomes de coluna de raw."""
    linha = {raw: PADRAO[tipo] for raw, _, tipo in transformacao.TABELAS[tabela]}
    linha.update(sobrescritas)
    return linha


def _inserir(con, tabela, linhas):
    if not linhas:
        return  # executemany do DuckDB não aceita lista vazia
    colunas = [raw for raw, _, _ in transformacao.TABELAS[tabela]]
    marcas = ", ".join("?" for _ in colunas)
    con.executemany(
        f"INSERT INTO raw.{tabela} VALUES ({marcas})",
        [[linha[c] for c in colunas] for linha in linhas],
    )


def _preparar(tmp_path, monkeypatch, dados=None, omitir=()):
    """Cria o schema raw com as tabelas pedidas (todas VARCHAR), no banco de tmp_path."""
    monkeypatch.setattr(db, "_RAIZ", tmp_path)
    con = duckdb.connect(str(tmp_path / "olist.duckdb"))
    con.execute("CREATE SCHEMA raw")
    for tabela, colunas in transformacao.TABELAS.items():
        if tabela in omitir:
            continue
        definicao = ", ".join(f"{raw} VARCHAR" for raw, _, _ in colunas)
        con.execute(f"CREATE TABLE raw.{tabela} ({definicao})")
        _inserir(con, tabela, (dados or {}).get(tabela, []))
    con.close()


def _executar(tmp_path, sql):
    con = duckdb.connect(str(tmp_path / "olist.duckdb"))
    con.execute(sql)
    con.close()


def _consultar(tmp_path, sql):
    con = duckdb.connect(str(tmp_path / "olist.duckdb"), read_only=True)
    linhas = con.execute(sql).fetchall()
    con.close()
    return linhas


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


def _tabela_existe(tmp_path, schema, tabela):
    achadas = _consultar(
        tmp_path,
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema = '{schema}' AND table_name = '{tabela}'",
    )
    return achadas == [(1,)]


# ------------------------------------------------------------------ escopo e nomes

def test_as_oito_tabelas_entram_e_geolocalizacao_fica_de_fora(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    _capturar(monkeypatch)
    transformacao.main()
    tabelas = _consultar(
        tmp_path,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'refined'",
    )
    assert sorted(t[0] for t in tabelas) == sorted(OITO)


def test_colunas_ganham_nomes_em_portugues_na_ordem_do_mapa(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    _capturar(monkeypatch)
    transformacao.main()
    colunas = _consultar(
        tmp_path,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'vendedores' "
        "ORDER BY ordinal_position",
    )
    assert colunas == [("vendedor_id",), ("cep_prefixo",), ("cidade",), ("uf",)]


def test_nenhuma_coluna_e_descartada(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    _capturar(monkeypatch)
    transformacao.main()
    for tabela in OITO:
        contar = ("SELECT count(*) FROM information_schema.columns "
                  "WHERE table_schema = '{}' AND table_name = '{}'")
        em_raw = _consultar(tmp_path, contar.format("raw", tabela))
        em_refined = _consultar(tmp_path, contar.format("refined", tabela))
        assert em_raw == em_refined


def test_coluna_fora_do_mapa_em_raw_para_a_transformacao(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    _executar(tmp_path, "ALTER TABLE raw.pedidos ADD COLUMN coluna_nova VARCHAR")
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        transformacao.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "coluna_nova" in erro
    assert not _tabela_existe(tmp_path, "refined", "pedidos")


# ------------------------------------------------------------------ tipos

def test_datas_com_hora_viram_timestamp_e_a_data_prevista_vira_date(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {"pedidos": [_linha("pedidos")]})
    _capturar(monkeypatch)
    transformacao.main()
    tipos = dict(_consultar(
        tmp_path,
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'pedidos'",
    ))
    assert tipos["data_compra"] == "TIMESTAMP"
    assert tipos["data_aprovacao"] == "TIMESTAMP"
    assert tipos["data_envio"] == "TIMESTAMP"
    assert tipos["data_entrega"] == "TIMESTAMP"
    assert tipos["data_entrega_prevista"] == "DATE"
    assert tipos["status"] == "VARCHAR"


def test_dinheiro_vira_decimal_e_contagem_vira_integer(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {"itens_pedido": [_linha("itens_pedido")]})
    _capturar(monkeypatch)
    transformacao.main()
    tipos = dict(_consultar(
        tmp_path,
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'itens_pedido'",
    ))
    assert tipos["preco"] == "DECIMAL(10,2)"
    assert tipos["frete"] == "DECIMAL(10,2)"
    assert tipos["item_seq"] == "INTEGER"
    assert tipos["pedido_id"] == "VARCHAR"


def test_a_soma_de_dinheiro_fecha_o_centavo(tmp_path, monkeypatch):
    # 0,10 + 0,20 em ponto flutuante não dá 0,30; em DECIMAL dá
    itens = [
        _linha("itens_pedido", order_item_id="1", price="0.10"),
        _linha("itens_pedido", order_item_id="2", price="0.20"),
    ]
    _preparar(tmp_path, monkeypatch, {"itens_pedido": itens})
    _capturar(monkeypatch)
    transformacao.main()
    soma = _consultar(tmp_path, "SELECT sum(preco) FROM refined.itens_pedido")
    assert soma == [(decimal.Decimal("0.30"),)]


def test_valores_de_data_e_hora_chegam_certos(tmp_path, monkeypatch):
    pedido = _linha(
        "pedidos",
        order_purchase_timestamp="2017-10-02 10:56:33",
        order_estimated_delivery_date="2017-10-18 00:00:00",
    )
    _preparar(tmp_path, monkeypatch, {"pedidos": [pedido]})
    _capturar(monkeypatch)
    transformacao.main()
    linha = _consultar(tmp_path, "SELECT data_compra, data_entrega_prevista FROM refined.pedidos")
    assert linha == [(dt.datetime(2017, 10, 2, 10, 56, 33), dt.date(2017, 10, 18))]


def test_data_de_criacao_com_hora_de_verao_vira_so_a_data(tmp_path, monkeypatch):
    # avaliação gravada às 01:00:00, efeito de horário de verão
    aval = _linha("avaliacoes", review_creation_date="2018-01-18 01:00:00")
    _preparar(tmp_path, monkeypatch, {"avaliacoes": [aval]})
    _capturar(monkeypatch)
    transformacao.main()
    assert _consultar(tmp_path, "SELECT data_criacao FROM refined.avaliacoes") == [(dt.date(2018, 1, 18),)]


def test_cep_continua_com_o_zero_a_esquerda(tmp_path, monkeypatch):
    cliente = _linha("clientes", customer_zip_code_prefix="01151")
    _preparar(tmp_path, monkeypatch, {"clientes": [cliente]})
    _capturar(monkeypatch)
    transformacao.main()
    linha = _consultar(
        tmp_path,
        "SELECT cep_prefixo, typeof(cep_prefixo) FROM refined.clientes",
    )
    assert linha == [("01151", "VARCHAR")]


# ------------------------------------------------------------------ conversão que falha

def test_valor_que_nao_converte_encerra_sem_virar_nulo(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {"itens_pedido": [_linha("itens_pedido", price="abc")]})
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        transformacao.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "itens_pedido" in erro
    assert "preco" in erro
    assert "'abc'" in erro
    assert not _tabela_existe(tmp_path, "refined", "itens_pedido")


def test_data_em_formato_errado_encerra_e_mostra_o_valor(tmp_path, monkeypatch):
    pedido = _linha("pedidos", order_purchase_timestamp="02/10/2017")
    _preparar(tmp_path, monkeypatch, {"pedidos": [pedido]})
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        transformacao.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "data_compra" in erro
    assert "'02/10/2017'" in erro


def test_o_valor_ruim_e_achado_no_meio_de_varias_linhas(tmp_path, monkeypatch):
    # 50 itens válidos, exceto o 37º
    itens = [
        _linha("itens_pedido", order_id=f"p{i}", price="quebrado" if i == 37 else "10.00")
        for i in range(50)
    ]
    _preparar(tmp_path, monkeypatch, {"itens_pedido": itens})
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        transformacao.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "'quebrado'" in erro


def test_duas_colunas_ruins_na_mesma_tabela_aparecem_juntas(tmp_path, monkeypatch):
    item = _linha("itens_pedido", price="abc", freight_value="xyz")
    _preparar(tmp_path, monkeypatch, {"itens_pedido": [item]})
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit):
        transformacao.main()
    _, erro = ler()
    assert "'abc'" in erro
    assert "'xyz'" in erro


# ------------------------------------------------------------------ duplicatas

def test_duplicata_exata_sai_e_e_contada(tmp_path, monkeypatch):
    # o pedido "a" chegou duas vezes, igualzinho; "b" é outro pedido
    a = _linha("pedidos", order_id="a")
    b = _linha("pedidos", order_id="b")
    _preparar(tmp_path, monkeypatch, {"pedidos": [a, a, b]})
    ler = _capturar(monkeypatch)
    transformacao.main()
    saida, _ = ler()
    assert _consultar(tmp_path, "SELECT count(*) FROM refined.pedidos") == [(2,)]
    assert "3 -> 2 linhas  (1 duplicatas)" in saida


def test_chave_repetida_com_conteudo_diferente_para_e_mostra_as_linhas(tmp_path, monkeypatch):
    # mesmo pedido, dois status
    um = _linha("pedidos", order_id="a", order_status="aprovado")
    dois = _linha("pedidos", order_id="a", order_status="enviado")
    _preparar(tmp_path, monkeypatch, {"pedidos": [um, dois]})
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        transformacao.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "Chave repetida com conteúdo diferente" in erro
    assert "aprovado" in erro and "enviado" in erro
    assert not _tabela_existe(tmp_path, "refined", "pedidos")


def test_mesma_avaliacao_em_dois_pedidos_nao_e_duplicata(tmp_path, monkeypatch):
    # avaliacao_id sozinho não é chave: a chave é (avaliacao_id, pedido_id)
    um = _linha("avaliacoes", review_id="r1", order_id="p1")
    dois = _linha("avaliacoes", review_id="r1", order_id="p2", review_score="5")
    _preparar(tmp_path, monkeypatch, {"avaliacoes": [um, dois]})
    _capturar(monkeypatch)
    transformacao.main()
    assert _consultar(tmp_path, "SELECT count(*) FROM refined.avaliacoes") == [(2,)]


# ------------------------------------------------------------------ nulos

def test_nulo_continua_nulo_a_linha_fica_e_a_tela_conta(tmp_path, monkeypatch):
    # pedido cancelado: nunca foi entregue, então não tem data de entrega
    cancelado = _linha(
        "pedidos", order_id="c", order_status="canceled",
        order_delivered_customer_date=None,
    )
    _preparar(tmp_path, monkeypatch, {"pedidos": [cancelado]})
    ler = _capturar(monkeypatch)
    transformacao.main()
    saida, _ = ler()
    assert _consultar(tmp_path, "SELECT status, data_entrega FROM refined.pedidos") == [("canceled", None)]
    assert "nulos mantidos: data_entrega 1" in saida


def test_tabela_sem_nulo_nao_ganha_linha_de_nulos(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {"pedidos": [_linha("pedidos")]})
    ler = _capturar(monkeypatch)
    transformacao.main()
    saida, _ = ler()
    assert "nulos mantidos" not in saida


# ------------------------------------------------------------------ saída, reexecução e erro

def test_milhar_com_ponto_na_saida(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    _executar(tmp_path, "INSERT INTO raw.pedidos (order_id) SELECT 'p' || i FROM range(1000) t(i)")
    ler = _capturar(monkeypatch)
    transformacao.main()
    saida, _ = ler()
    assert "1.000 -> 1.000 linhas  (0 duplicatas)" in saida
    assert "Total: 1.000 linhas" in saida


def test_rodar_duas_vezes_da_a_mesma_saida(tmp_path, monkeypatch):
    a = _linha("pedidos", order_id="a")
    _preparar(tmp_path, monkeypatch, {"pedidos": [a, a]})
    ler = _capturar(monkeypatch)
    transformacao.main()
    primeira, _ = ler()
    ler = _capturar(monkeypatch)
    transformacao.main()
    segunda, _ = ler()
    assert primeira == segunda
    assert _consultar(tmp_path, "SELECT count(*) FROM refined.pedidos") == [(1,)]


def test_raw_nao_e_alterado(tmp_path, monkeypatch):
    a = _linha("pedidos", order_id="a")
    _preparar(tmp_path, monkeypatch, {"pedidos": [a, a]})
    _capturar(monkeypatch)
    transformacao.main()
    assert _consultar(tmp_path, "SELECT count(*) FROM raw.pedidos") == [(2,)]
    tabelas = _consultar(
        tmp_path,
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'raw'",
    )
    assert tabelas == [(len(OITO),)]


def test_tabela_faltando_em_raw_lista_e_manda_rodar_a_ingestao(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, omitir=("avaliacoes", "produtos"))
    ler = _capturar(monkeypatch)
    with pytest.raises(SystemExit) as encerrou:
        transformacao.main()
    _, erro = ler()
    assert encerrou.value.code == 1
    assert "avaliacoes" in erro and "produtos" in erro
    assert "pipeline.ingestao" in erro
    schemas = _consultar(
        tmp_path,
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'refined'",
    )
    assert schemas == [(0,)]
