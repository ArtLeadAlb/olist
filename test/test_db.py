"""Testes de pipeline/db.py: caminhos, schema e gravação, sempre em tmp_path."""

import importlib

import duckdb
import pandas as pd

from pipeline import db


def _banco(tmp_path):
    return duckdb.connect(str(tmp_path / "teste.duckdb"))


def test_importar_db_nao_cria_arquivo_nenhum():
    antes = set(db._RAIZ.iterdir())
    importlib.reload(db)
    assert set(db._RAIZ.iterdir()) == antes


def test_conectar_cria_o_banco_na_raiz_e_nao_na_pasta_corrente(tmp_path, monkeypatch):
    raiz = tmp_path / "raiz"
    outra = tmp_path / "outra"
    raiz.mkdir()
    outra.mkdir()
    monkeypatch.setattr(db, "_RAIZ", raiz)
    monkeypatch.chdir(outra)
    con = db.conectar()
    con.close()
    assert (raiz / "olist.duckdb").exists()
    assert not (outra / "olist.duckdb").exists()


def test_conectar_devolve_a_conexao_aberta_para_quem_chamou(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_RAIZ", tmp_path)
    con = db.conectar()
    resposta = con.execute("SELECT 42").fetchall()
    con.close()
    assert resposta == [(42,)]


def test_conectar_nao_guarda_conexao_global(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_RAIZ", tmp_path)
    primeira = db.conectar()
    segunda = db.conectar()
    primeira.close()
    segunda.close()
    assert primeira is not segunda


def test_caminhos_nao_dependem_do_diretorio_corrente(tmp_path, monkeypatch):
    raiz_antes, raw_antes = db._RAIZ, db.PASTA_RAW
    monkeypatch.chdir(tmp_path)
    importlib.reload(db)
    assert (db._RAIZ, db.PASTA_RAW) == (raiz_antes, raw_antes)
    assert db.PASTA_RAW == db._RAIZ / "raw"


def test_criar_schema_pode_rodar_duas_vezes(tmp_path):
    con = _banco(tmp_path)
    db.criar_schema(con, "raw")
    db.criar_schema(con, "raw")
    existentes = con.execute(
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'raw'"
    ).fetchall()
    con.close()
    assert existentes == [(1,)]


def test_gravar_devolve_a_contagem_lida_do_banco(tmp_path):
    con = _banco(tmp_path)
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"a": ["1", "2", "3"]}, dtype=str)
    primeira = db.gravar(con, df, "raw", "t")
    segunda = db.gravar(con, df, "raw", "t")
    con.close()
    assert (primeira, segunda) == (3, 3)


def test_gravar_recria_a_tabela_em_vez_de_acrescentar(tmp_path):
    con = _banco(tmp_path)
    db.criar_schema(con, "raw")
    db.gravar(con, pd.DataFrame({"a": ["1", "2", "3"]}, dtype=str), "raw", "t")
    contagem = db.gravar(con, pd.DataFrame({"a": ["9", "8"]}, dtype=str), "raw", "t")
    valores = con.execute("SELECT a FROM raw.t ORDER BY a").fetchall()
    con.close()
    assert contagem == 2
    assert valores == [("8",), ("9",)]


def test_gravar_coluna_str_vira_varchar_e_nulo_continua_nulo(tmp_path):
    con = _banco(tmp_path)
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"a": ["x", None, "z"]}, dtype=str)
    db.gravar(con, df, "raw", "t")
    tipo = con.execute(
        "SELECT data_type FROM information_schema.columns WHERE table_name = 't'"
    ).fetchall()
    nulos = con.execute("SELECT count(*) FROM raw.t WHERE a IS NULL").fetchall()
    vazios = con.execute("SELECT count(*) FROM raw.t WHERE a = ''").fetchall()
    con.close()
    assert tipo == [("VARCHAR",)]
    assert nulos == [(1,)]
    assert vazios == [(0,)]


def test_gravar_nao_converte_o_tipo_do_dataframe(tmp_path):
    con = _banco(tmp_path)
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"n": [1, 2, 3]})
    db.gravar(con, df, "raw", "t")
    tipo = con.execute(
        "SELECT data_type FROM information_schema.columns WHERE table_name = 't'"
    ).fetchall()
    con.close()
    assert tipo == [("BIGINT",)]


def test_gravar_nao_deixa_view_nem_tabela_temporaria_para_tras(tmp_path):
    con = _banco(tmp_path)
    db.criar_schema(con, "raw")
    db.gravar(con, pd.DataFrame({"a": ["1"]}, dtype=str), "raw", "t")
    views = con.execute("SELECT count(*) FROM duckdb_views() WHERE NOT internal").fetchall()
    tabelas = con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE NOT internal"
    ).fetchall()
    con.close()
    assert views == [(0,)]
    assert tabelas == [("t",)]
