"""Explorar o olist.duckdb pelo navegador (DuckDB UI).

Execução:
    uv run python ui.py

SPEC (e o porquê de cada regra)

U1. O QUE FAZ
    Abre o olist.duckdb da raiz do projeto, instala e carrega a extensão `ui`
    (INSTALL ui; LOAD ui;) e chama CALL start_ui(), que sobe o servidor em
    http://localhost:4213 e abre o navegador.
    Por quê: explorar tabelas no navegador é mais rápido do que ler tabela no
    terminal.

U2. FICA DE PÉ ATÉ CTRL+C
    A extensão serve enquanto a conexão estiver viva. O script mantém o
    processo rodando, imprime a URL e "Ctrl+C para encerrar", e no Ctrl+C
    fecha a conexão e sai limpo, sem traceback.
    Por quê: o arquivo .duckdb aceita um único processo escrevendo. Com o
    ui.py de pé, a ingestão falha com "Could not set lock on file". Saber
    exatamente como desligar o servidor faz parte da ferramenta.

U3. NÃO CRIA BANCO
    Se olist.duckdb não existir, diz que é preciso rodar a ingestão antes e
    encerra com sys.exit(1). Não usa conectar() de pipeline/db.py.
    Por quê: conectar() cria o arquivo quando ele falta, e um banco vazio
    aberto no navegador parece ingestão quebrada.

U4. SEPARAÇÃO
    ui.py não importa pipeline/ingestao.py (nem nada de pipeline/), e a
    ingestão não importa ui.py.
    Por quê: a ingestão não pode subir servidor, abrir navegador nem depender
    da extensão ui para rodar.

U5. SAÍDA NA TELA
    stdout reconfigurado para utf-8, pelo mesmo motivo da ingestão (acento no
    Prompt de Comando do Windows).

CRITÉRIOS DE ACEITE
- uv run python ui.py abre o navegador em localhost:4213 e o schema raw
  aparece com as nove tabelas.
- Ctrl+C devolve o terminal sem traceback, e logo depois a ingestão roda sem
  erro de lock.
- Renomear olist.duckdb faz o ui.py parar com a mensagem, sem criar arquivo
  novo.
"""

import sys
import time
from pathlib import Path

import duckdb

BANCO = Path(__file__).resolve().parent / "olist.duckdb"
URL = "http://localhost:4213"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    if not BANCO.is_file():
        print(
            f"{BANCO} não existe. Rode a ingestão antes: "
            "uv run python -m pipeline.ingestao",
            file=sys.stderr,
        )
        sys.exit(1)

    con = duckdb.connect(str(BANCO))
    try:
        con.execute("INSTALL ui")
        con.execute("LOAD ui")
        con.execute("CALL start_ui()")
        print(f"DuckDB UI em {URL}")
        print("Ctrl+C para encerrar")
        # sleep em laço, e não Event().wait() sem timeout: no Windows uma
        # espera sem timeout pode não ser interrompida pelo Ctrl+C.
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        con.close()


if __name__ == "__main__":
    main()
