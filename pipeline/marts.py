"""Marts da Olist: de sql/marts/*.sql para o schema `marts`.

Execução:
    uv run python -m pipeline.marts

SPEC (e o porquê de cada regra)

1. ESCOPO
   Lê de refined, escreve no schema marts. Nunca escreve em raw nem em
   refined. O schema marts é apagado e recriado a cada execução
   (DROP SCHEMA IF EXISTS marts CASCADE).
   Por quê: um mart cujo arquivo foi apagado não pode continuar existindo
   no banco.

2. UM ARQUIVO, UMA TABELA
   Lê todos os sql/marts/*.sql em ordem alfabética. Nome da tabela = nome do
   arquivo sem a extensão e sem o prefixo numérico:
     sql/marts/01_vendas_mensais.sql -> marts.vendas_mensais
   Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>
   Tira espaços e um ponto e vírgula do final do conteúdo, e nada mais. O
   Python não altera, não monta e não completa a SQL.
   Por quê: a regra de negócio mora inteira no arquivo .sql.

3. SAÍDA NA TELA
   Uma linha por mart, com a contagem vinda do banco, milhar com ponto:
     ✓ marts.vendas_mensais        24 linhas
   Linha final com o número de marts e o total de linhas. stdout
   reconfigurado para utf-8.
   Por quê: é o instrumento de conferência da etapa, e o Prompt de Comando
   do Windows embaralha acento (e o ✓) por padrão.

4. ERRO
   Antes de tudo: se faltar qualquer uma das oito tabelas em refined, lista
   quais, diz para rodar "uv run python -m pipeline.transformacao" e encerra
   com sys.exit(1).
   Se um .sql falhar: mostra o nome do arquivo e a mensagem do DuckDB, não
   executa os seguintes, sys.exit(1).
   Se um mart voltar com zero linhas: mostra o nome e encerra com
   sys.exit(1). Por quê: mart vazio é quase sempre um JOIN que não casou, e
   um dashboard vazio parece um negócio parado.
   Se sql/marts/ não tiver nenhum arquivo: avisa e sys.exit(1).
   Antes de executar qualquer SQL: arquivo sem prefixo NN_ ou dois arquivos
   que dão o mesmo nome de tabela -> lista quais e sys.exit(1).
   Tudo roda numa transação só: se qualquer passo falhar (inclusive o mart
   vazio), o schema marts volta a ser o da última execução que deu certo.
   Por quê: um schema pela metade quebra o dashboard sem avisar.

CRITÉRIOS DE ACEITE
- Com um arquivo sql/marts/00_teste.sql contendo "SELECT 1 AS x", cria
  marts.teste com 1 linha.
- Apagar o arquivo e rodar de novo faz marts.teste desaparecer.
- Um arquivo com erro de sintaxe para tudo, com o nome do arquivo na tela,
  e marts continua exatamente como estava antes da execução.
- Um arquivo teste.sql, sem prefixo, para antes de executar qualquer SQL.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import re
import sys
from pathlib import Path

import duckdb

from pipeline.db import conectar, criar_schema

ORIGEM = "refined"
DESTINO = "marts"
PASTA_MARTS = Path(__file__).resolve().parent.parent / "sql" / "marts"

TABELAS_ENTRADA = [
    "pedidos", "itens_pedido", "pagamentos", "clientes",
    "vendedores", "produtos", "traducao_categorias", "avaliacoes",
]

PADRAO_ARQUIVO = re.compile(r"(\d{2})_(.+)\.sql", re.IGNORECASE)


class _Falha(Exception):
    def __init__(self, *linhas: str):
        super().__init__(linhas[0])
        self.linhas = linhas


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _erro(*linhas: str) -> None:
    for linha in linhas:
        print(linha, file=sys.stderr)
    sys.exit(1)


def _verificar_entrada(con) -> None:
    existentes = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [ORIGEM],
        ).fetchall()
    }
    faltando = [t for t in TABELAS_ENTRADA if t not in existentes]
    if faltando:
        _erro(
            f"Tabelas ausentes em {ORIGEM}: {', '.join(faltando)}",
            "Rode primeiro: uv run python -m pipeline.transformacao",
        )


def _listar_marts() -> list[tuple[Path, str]]:
    arquivos = sorted(PASTA_MARTS.glob("*.sql"), key=lambda p: p.name)
    if not arquivos:
        _erro(f"Nenhum arquivo .sql em {PASTA_MARTS}.")

    sem_prefixo = [a.name for a in arquivos if not PADRAO_ARQUIVO.fullmatch(a.name)]
    por_nome: dict[str, list[str]] = {}
    for a in arquivos:
        m = PADRAO_ARQUIVO.fullmatch(a.name)
        if m:
            # casefold: o DuckDB trata Teste e teste como a mesma tabela.
            por_nome.setdefault(m.group(2).casefold(), []).append(a.name)
    repetidos = {n: fs for n, fs in por_nome.items() if len(fs) > 1}

    problemas = []
    if sem_prefixo:
        problemas.append("Arquivos sem o prefixo NN_ (dois dígitos e sublinhado):")
        problemas.extend(f"  - {nome}" for nome in sem_prefixo)
    for nome, fs in repetidos.items():
        problemas.append(f"Arquivos que dão a mesma tabela {DESTINO}.{nome}:")
        problemas.extend(f"  - {f}" for f in fs)
    if problemas:
        _erro(*problemas)

    return [(a, PADRAO_ARQUIVO.fullmatch(a.name).group(2)) for a in arquivos]


def _conteudo(caminho: Path) -> str:
    # utf-8-sig: editores do Windows podem gravar BOM, que quebraria a SQL.
    texto = caminho.read_text(encoding="utf-8-sig").rstrip()
    if texto.endswith(";"):
        texto = texto[:-1].rstrip()
    return texto


def _executar(con, marts: list[tuple[Path, str]]) -> list[tuple[str, int]]:
    con.execute(f"DROP SCHEMA IF EXISTS {DESTINO} CASCADE")
    criar_schema(con, DESTINO)
    resultados = []
    for caminho, nome in marts:
        try:
            con.execute(f"CREATE TABLE {DESTINO}.{nome} AS {_conteudo(caminho)}")
        except duckdb.Error as e:
            raise _Falha(f"Falha em {caminho.name}:", str(e)) from e
        # fetchall, não fetchone: fetchone deixa o resultado aberto na conexão.
        linhas = con.execute(f"SELECT count(*) FROM {DESTINO}.{nome}").fetchall()[0][0]
        if linhas == 0:
            raise _Falha(f"{DESTINO}.{nome} ({caminho.name}) voltou com zero linhas.")
        resultados.append((nome, linhas))
    return resultados


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        _verificar_entrada(con)
        marts = _listar_marts()

        con.execute("BEGIN")
        try:
            resultados = _executar(con, marts)
        except _Falha as falha:
            con.execute("ROLLBACK")
            _erro(*falha.linhas)
        except BaseException:
            con.execute("ROLLBACK")
            raise
        con.execute("COMMIT")

        # Só imprime depois do COMMIT: um ✓ de mart que sofreu rollback
        # seria mentira na tela.
        largura = max(len(f"{DESTINO}.{n}") for n, _ in resultados) + 2
        total = 0
        for nome, linhas in resultados:
            total += linhas
            print(f"✓ {f'{DESTINO}.{nome}'.ljust(largura)}{_milhar(linhas)} linhas")
        print(f"{len(resultados)} marts, {_milhar(total)} linhas no total")
    finally:
        con.close()


if __name__ == "__main__":
    main()
