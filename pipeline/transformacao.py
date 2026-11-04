"""Transformação da Olist: do schema `raw` para o schema `refined`.

Execução:
    uv run python -m pipeline.transformacao

SPEC (e o porquê de cada regra)

1. ESCOPO
   Lê de raw, escreve em refined. Nunca escreve em raw.
   Entram oito tabelas: pedidos, itens_pedido, pagamentos, clientes,
   vendedores, produtos, traducao_categorias, avaliacoes.
   Fica de fora: geolocalizacao.
   Por quê: nenhum mart do curso usa. Não se limpa o que ninguém vai ler.

2. NOMES
   Colunas renomeadas para português, snake_case, pelo mapa TABELAS abaixo,
   completo e literal. Nenhuma coluna fora do mapa; nenhuma descartada.
   Por quê: é o vocabulário que o autor digita de memória nos JOINs da aula 3.

3. TIPOS
   Datas com hora: TIMESTAMP, formato declarado '%Y-%m-%d %H:%M:%S'
     (data_compra, data_aprovacao, data_envio, data_entrega,
      data_limite_envio, data_resposta).
   data_entrega_prevista: DATE. Por quê: a hora é sempre 00:00:00 nas 99.441
     linhas; guardar a hora seria inventar precisão.
   data_criacao: DATE. Por quê: a hora é 00:00:00 em 99.139 das 99.224
     avaliações; nas outras 85 é 01:00:00, efeito de horário de verão, e não
     um horário de verdade.
   Dinheiro (preco, frete, valor): DECIMAL(10,2). Por quê: DOUBLE não
     representa centavos com exatidão, e soma de dinheiro tem que fechar.
   Contagens e medidas (item_seq, pagamento_seq, parcelas, tamanho_nome,
     tamanho_descricao, qtd_fotos, peso_g, comprimento_cm, altura_cm,
     largura_cm, nota): INTEGER.
   Todo o resto continua VARCHAR, inclusive cep_prefixo. Por quê: 23.995
     clientes têm CEP começando com zero; CEP é identificador, nunca é
     somado, e como número perderia o zero.
   A conversão é feita em SQL pelo DuckDB (strptime, CAST), disparada pelo
   Python. Por quê: o dado já está no banco; não há por que trazê-lo para a
   memória só para converter tipo.

4. CONVERSÃO QUE FALHA
   Para tudo. Usa strptime e CAST, que estouram; nunca try_strptime, TRY_CAST
   ou errors="coerce", que transformam falha em nulo. Ao falhar: diz tabela,
   coluna e um exemplo do valor que não converteu, e encerra com sys.exit(1).
   Por quê: um nulo fabricado pela conversão fica indistinguível de um nulo
   verdadeiro do dado, para sempre.

5. DUPLICATAS
   Chave de cada tabela: ver CHAVES abaixo. Em avaliacoes, avaliacao_id
   sozinho não é chave: o mesmo id aparece em mais de um pedido.
   Linha inteira repetida: mantém uma, e conta quantas saíram.
   Chave repetida com conteúdo diferente: para, mostra a chave e as linhas
   conflitantes, sys.exit(1). Não escolhe uma por conta própria.
   Por quê: escolher em silêncio é decidir sem dizer que decidiu.

6. NULOS
   Nenhuma linha é apagada por ter nulo. Nenhum nulo é preenchido.
   Por quê: nas datas de pedidos, o nulo é informação (pedido cancelado não
   tem data de entrega porque não foi entregue). Em produtos, os 610 sem
   categoria continuam sem categoria: dar rótulo a eles é decisão de mart
   (aula 3), não de refined. Em avaliacoes, título e comentário nulos
   continuam nulos: avaliação sem texto é a regra, não a exceção. Anomalias
   de negócio também ficam (8 pedidos delivered sem data_entrega, 166 com
   data_envio antes da data_compra, pedidos com mais de uma avaliação).
   refined não corrige fato; quem decide o que fazer com ele é a pergunta
   que o mart responde.

7. SAÍDA NA TELA
   Uma linha por tabela:
     refined.pedidos            99.441 -> 99.441 linhas  (0 duplicatas)
   Abaixo, indentadas, as colunas com nulo e a contagem:
       nulos mantidos: data_aprovacao 160, data_envio 1.783, data_entrega 2.965
   Contagens vêm do banco, milhar separado por ponto. Linha final com o
   total. stdout reconfigurado para utf-8.
   Por quê: é o instrumento de conferência da etapa. O utf-8 é necessário
   porque o Prompt de Comando do Windows embaralha acento por padrão.

REEXECUÇÃO
   CREATE OR REPLACE TABLE, nunca acrescenta. Rodar dez vezes = rodar uma.

ERRO
   Antes de transformar, verifica se as oito tabelas de entrada existem em
   raw. Faltando qualquer uma: lista quais, manda rodar
   "uv run python -m pipeline.ingestao" e encerra com sys.exit(1).
   Por quê: transformar parte do que deveria existir produz um refined que
   parece completo e não é.

CRITÉRIOS DE ACEITE
- Oito tabelas em refined; em cada uma, linhas que saem = linhas que entram
  (com este dado, 0 duplicatas em todas). Total: 550.759.
- DESCRIBE refined.pedidos mostra TIMESTAMP nas datas com hora e DATE em
  data_entrega_prevista.
- Nulos depois = nulos antes, coluna por coluna (pedidos: 160 / 1.783 /
  2.965; produtos: 610 em categoria; avaliacoes: 87.656 em titulo, 58.247
  em comentario).
- sum(preco) em refined.itens_pedido bate com sum(CAST(price AS DECIMAL))
  em raw, centavo por centavo.
- cep_prefixo continua com o zero à esquerda: '01151' e não 1151.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import sys

import duckdb

from pipeline.db import conectar, criar_schema

ORIGEM = "raw"
DESTINO = "refined"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
MAX_CHAVES_MOSTRADAS = 5

TXT, TS, DATA, DEC, INT = "VARCHAR", "TIMESTAMP", "DATE", "DECIMAL(10,2)", "INTEGER"

# tabela -> [(coluna em raw, coluna em refined, tipo)]
TABELAS = {
    "pedidos": [
        ("order_id", "pedido_id", TXT),
        ("customer_id", "cliente_id", TXT),
        ("order_status", "status", TXT),
        ("order_purchase_timestamp", "data_compra", TS),
        ("order_approved_at", "data_aprovacao", TS),
        ("order_delivered_carrier_date", "data_envio", TS),
        ("order_delivered_customer_date", "data_entrega", TS),
        ("order_estimated_delivery_date", "data_entrega_prevista", DATA),
    ],
    "itens_pedido": [
        ("order_id", "pedido_id", TXT),
        ("order_item_id", "item_seq", INT),
        ("product_id", "produto_id", TXT),
        ("seller_id", "vendedor_id", TXT),
        ("shipping_limit_date", "data_limite_envio", TS),
        ("price", "preco", DEC),
        ("freight_value", "frete", DEC),
    ],
    "pagamentos": [
        ("order_id", "pedido_id", TXT),
        ("payment_sequential", "pagamento_seq", INT),
        ("payment_type", "tipo", TXT),
        ("payment_installments", "parcelas", INT),
        ("payment_value", "valor", DEC),
    ],
    "clientes": [
        ("customer_id", "cliente_id", TXT),
        ("customer_unique_id", "cliente_unico_id", TXT),
        ("customer_zip_code_prefix", "cep_prefixo", TXT),
        ("customer_city", "cidade", TXT),
        ("customer_state", "uf", TXT),
    ],
    "vendedores": [
        ("seller_id", "vendedor_id", TXT),
        ("seller_zip_code_prefix", "cep_prefixo", TXT),
        ("seller_city", "cidade", TXT),
        ("seller_state", "uf", TXT),
    ],
    "produtos": [
        ("product_id", "produto_id", TXT),
        ("product_category_name", "categoria", TXT),
        ("product_name_lenght", "tamanho_nome", INT),
        ("product_description_lenght", "tamanho_descricao", INT),
        ("product_photos_qty", "qtd_fotos", INT),
        ("product_weight_g", "peso_g", INT),
        ("product_length_cm", "comprimento_cm", INT),
        ("product_height_cm", "altura_cm", INT),
        ("product_width_cm", "largura_cm", INT),
    ],
    "traducao_categorias": [
        ("product_category_name", "categoria", TXT),
        ("product_category_name_english", "categoria_en", TXT),
    ],
    "avaliacoes": [
        ("review_id", "avaliacao_id", TXT),
        ("order_id", "pedido_id", TXT),
        ("review_score", "nota", INT),
        ("review_comment_title", "titulo", TXT),
        ("review_comment_message", "comentario", TXT),
        ("review_creation_date", "data_criacao", DATA),
        ("review_answer_timestamp", "data_resposta", TS),
    ],
}

# Colunas da chave, com os nomes de refined.
CHAVES = {
    "pedidos": ["pedido_id"],
    "itens_pedido": ["pedido_id", "item_seq"],
    "pagamentos": ["pedido_id", "pagamento_seq"],
    "clientes": ["cliente_id"],
    "vendedores": ["vendedor_id"],
    "produtos": ["produto_id"],
    "traducao_categorias": ["categoria"],
    "avaliacoes": ["avaliacao_id", "pedido_id"],
}


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _erro(*linhas: str) -> None:
    for linha in linhas:
        print(linha, file=sys.stderr)
    sys.exit(1)


def _expr(tipo: str, coluna: str) -> str:
    # Só strptime e CAST: ambos estouram em vez de virar nulo (spec, item 4).
    if tipo == TS:
        return f"strptime({coluna}, '{FORMATO_DATA}')"
    if tipo == DATA:
        return f"CAST(strptime({coluna}, '{FORMATO_DATA}') AS DATE)"
    if tipo in (DEC, INT):
        return f"CAST({coluna} AS {tipo})"
    return coluna


def _contar(con, schema: str, tabela: str) -> int:
    # fetchall, não fetchone: fetchone deixa o resultado aberto e a próxima
    # operação na conexão pode falhar com ResourceInUseException.
    return con.execute(f"SELECT count(*) FROM {schema}.{tabela}").fetchall()[0][0]


def _verificar_entrada(con) -> None:
    existentes = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [ORIGEM],
        ).fetchall()
    }
    faltando = [t for t in TABELAS if t not in existentes]
    if faltando:
        _erro(
            f"Tabelas ausentes em {ORIGEM}: {', '.join(faltando)}",
            "Rode primeiro: uv run python -m pipeline.ingestao",
        )


def _verificar_colunas(con, tabela: str) -> None:
    # "Nenhuma coluna fora do mapa; nenhuma descartada": se raw divergir do
    # mapa, melhor parar do que descartar ou inventar coluna em silêncio.
    reais = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ?",
            [ORIGEM, tabela],
        ).fetchall()
    }
    mapa = {raw for raw, _, _ in TABELAS[tabela]}
    if reais != mapa:
        _erro(
            f"{ORIGEM}.{tabela} não bate com o mapa de colunas.",
            f"  só em raw: {sorted(reais - mapa) or '-'}",
            f"  só no mapa: {sorted(mapa - reais) or '-'}",
        )


def _verificar_conflitos(con, tabela: str) -> None:
    novo_para_raw = {novo: raw for raw, novo, _ in TABELAS[tabela]}
    chave = [novo_para_raw[c] for c in CHAVES[tabela]]
    cols = ", ".join(chave)
    unicas = f"(SELECT DISTINCT * FROM {ORIGEM}.{tabela})"
    repetidas = con.execute(
        f"SELECT {cols} FROM {unicas} GROUP BY {cols} "
        f"HAVING count(*) > 1 ORDER BY {cols} LIMIT {MAX_CHAVES_MOSTRADAS}"
    ).fetchall()
    if not repetidas:
        return
    saida = [f"Chave repetida com conteúdo diferente em {DESTINO}.{tabela} "
             f"(chave: {', '.join(CHAVES[tabela])})."]
    cond = " AND ".join(f"{c} IS NOT DISTINCT FROM ?" for c in chave)
    for valores in repetidas:
        saida.append(f"  chave {valores}:")
        linhas = con.execute(
            f"SELECT * FROM {unicas} WHERE {cond}", list(valores)
        ).fetchall()
        saida.extend(f"    {linha}" for linha in linhas)
    _erro(*saida)


def _estoura(con, tabela: str, expr: str, lo=None, hi=None) -> bool:
    filtro = "" if lo is None else f" WHERE rowid BETWEEN {lo} AND {hi}"
    try:
        # count(expr) obriga o DuckDB a avaliar a conversão em cada linha.
        con.execute(f"SELECT count({expr}) FROM {ORIGEM}.{tabela}{filtro}").fetchall()
    except duckdb.Error:
        return True
    return False


def _valor_que_falha(con, tabela: str, raw: str, expr: str):
    # O erro do DuckDB não traz o valor de forma confiável, e try_* é proibido
    # pela spec. Então bisseção por rowid, só com conversões estritas: a cada
    # passo, a metade que ainda estoura contém uma linha ruim.
    lo, hi = con.execute(
        f"SELECT min(rowid), max(rowid) FROM {ORIGEM}.{tabela}"
    ).fetchall()[0]
    while lo < hi:
        meio = (lo + hi) // 2
        if _estoura(con, tabela, expr, lo, meio):
            hi = meio
        else:
            lo = meio + 1
    return con.execute(
        f"SELECT {raw} FROM {ORIGEM}.{tabela} WHERE rowid = {lo}"
    ).fetchall()[0][0]


def _diagnosticar(con, tabela: str) -> None:
    saida = []
    for raw, novo, tipo in TABELAS[tabela]:
        if tipo == TXT:
            continue
        expr = _expr(tipo, raw)
        if _estoura(con, tabela, expr):
            valor = _valor_que_falha(con, tabela, raw, expr)
            saida.append(
                f"Falha de conversão em {DESTINO}.{tabela}: coluna {novo} "
                f"(raw: {raw}), valor {valor!r} não converte para {tipo}."
            )
    if saida:
        _erro(*saida)


def _converter(con, tabela: str) -> None:
    selecao = ", ".join(f"{_expr(t, raw)} AS {novo}" for raw, novo, t in TABELAS[tabela])
    try:
        con.execute(
            f"CREATE OR REPLACE TABLE {DESTINO}.{tabela} AS "
            f"SELECT {selecao} FROM (SELECT DISTINCT * FROM {ORIGEM}.{tabela})"
        )
    except duckdb.Error:
        _diagnosticar(con, tabela)  # encerra com exit(1) se achar a coluna
        raise  # não era conversão (ex.: lock): deixa o erro original aparecer


def _nulos(con, tabela: str) -> list[tuple[str, int]]:
    colunas = [novo for _, novo, _ in TABELAS[tabela]]
    partes = ", ".join(f"count(*) FILTER (WHERE {c} IS NULL)" for c in colunas)
    contagens = con.execute(f"SELECT {partes} FROM {DESTINO}.{tabela}").fetchall()[0]
    return [(c, n) for c, n in zip(colunas, contagens) if n]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        _verificar_entrada(con)
        criar_schema(con, DESTINO)

        largura = max(len(f"{DESTINO}.{t}") for t in TABELAS) + 1
        total = 0
        for tabela in TABELAS:
            _verificar_colunas(con, tabela)
            entrada = _contar(con, ORIGEM, tabela)
            _verificar_conflitos(con, tabela)
            _converter(con, tabela)
            saida = _contar(con, DESTINO, tabela)
            total += saida

            nome = f"{DESTINO}.{tabela}".ljust(largura)
            print(f"{nome}{_milhar(entrada)} -> {_milhar(saida)} linhas  "
                  f"({_milhar(entrada - saida)} duplicatas)")
            nulos = _nulos(con, tabela)
            if nulos:
                itens = ", ".join(f"{c} {_milhar(n)}" for c, n in nulos)
                print(f"    nulos mantidos: {itens}")
        print(f"Total: {_milhar(total)} linhas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
