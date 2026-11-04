"""Ingestão da Olist: dos nove .csv.gz para o schema `raw` do olist.duckdb.

Execução:
    uv run python -m pipeline.ingestao

SPEC (e o porquê de cada regra)

1. ESCOPO E NOMES
   Destino: schema `raw`. Cada arquivo vira uma tabela com nome em português
   (mapa em ARQUIVO_PARA_TABELA). Os nomes são em português porque é o
   vocabulário que o autor digita de memória nos JOINs das próximas aulas.
   O mapa é completo e literal: arquivo fora dele não entra.

2. PROIBIÇÕES
   Nenhuma conversão de tipo, nenhuma linha descartada ou deduplicada,
   nenhum nome de coluna alterado, nenhum valor corrigido, preenchido ou
   normalizado. Data continua texto, nulo continua nulo.
   Por quê: a fronteira entre "o dado que chegou" e "o dado que eu decidi"
   precisa existir em algum lugar, e esse lugar é a passagem de raw para
   refined (etapa 2). Se a correção acontecer aqui, a fronteira some.

3. REEXECUÇÃO
   Rodar dez vezes dá o mesmo resultado que rodar uma: a tabela é recriada
   (CREATE OR REPLACE), nunca acrescentada (responsabilidade de `gravar`).
   Por quê: é o que permite errar sem medo.

4. LEITURA DO ARQUIVO
   encoding declarado como utf-8, nunca adivinhado. Os .csv.gz são lidos
   direto, sem descompactar. Campo vazio vira nulo, não string vazia.
   Por quê: adivinhar encoding falha em silêncio; descompactar deixaria
   arquivos soltos no disco para manter e conferir.

5. TIPAGEM
   Toda coluna entra como texto (dtype=str), inferência desligada.
   Por quê: a inferência lê CEP com zero à esquerda como número e o zero
   desaparece sem aviso. A conversão acontece na etapa 2, onde é uma
   decisão registrada.

6. SAÍDA NA TELA
   Uma linha por tabela, com nome qualificado e contagem de linhas vinda do
   banco (não do DataFrame), milhar separado por ponto. Uma linha final com
   o total. stdout reconfigurado para utf-8.
   Por quê: esta saída é o único instrumento de conferência da etapa. A
   contagem vem do banco porque é ele que prova o que foi gravado. O utf-8
   é necessário porque o Prompt de Comando do Windows embaralha acento por
   padrão.

7. ERRO
   Antes de abrir o banco, verifica se os nove arquivos existem. Faltando
   qualquer um: lista os que faltam, diz em que pasta procurou e encerra com
   sys.exit(1). Não ingere parcialmente.
   Por quê: ingerir oito de nove tabelas em silêncio produz um dashboard
   errado que parece certo. A checagem vem antes de abrir o banco porque
   conectar() cria o arquivo quando ele falta.

CRITÉRIOS DE ACEITE
- A execução imprime nove linhas e um total de 1.550.922 registros.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
- SELECT * FROM raw.pedidos devolve todas as colunas como VARCHAR.
- Remover um arquivo da pasta faz o script parar antes de gravar qualquer
  tabela.
- O script termina sozinho e devolve o terminal.
"""

import sys

import pandas as pd

from pipeline.db import PASTA_RAW, conectar, criar_schema, gravar

SCHEMA = "raw"

ARQUIVO_PARA_TABELA = {
    "olist_orders_dataset.csv.gz": "pedidos",
    "olist_order_items_dataset.csv.gz": "itens_pedido",
    "olist_order_payments_dataset.csv.gz": "pagamentos",
    "olist_order_reviews_dataset.csv.gz": "avaliacoes",
    "olist_customers_dataset.csv.gz": "clientes",
    "olist_sellers_dataset.csv.gz": "vendedores",
    "olist_products_dataset.csv.gz": "produtos",
    "product_category_name_translation.csv.gz": "traducao_categorias",
    "olist_geolocation_dataset.csv.gz": "geolocalizacao",
}


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _verificar_arquivos() -> None:
    faltando = [a for a in ARQUIVO_PARA_TABELA if not (PASTA_RAW / a).is_file()]
    if faltando:
        print(f"Arquivos não encontrados em {PASTA_RAW}:", file=sys.stderr)
        for arquivo in faltando:
            print(f"  - {arquivo}", file=sys.stderr)
        sys.exit(1)


def _ler(arquivo: str) -> pd.DataFrame:
    return pd.read_csv(
        PASTA_RAW / arquivo,
        dtype=str,
        encoding="utf-8",
        compression="gzip",
        # Por padrão o pandas também vira nulo textos como "NA", "null" e
        # "NaN". Isso seria corrigir valor. Só o campo vazio vira nulo.
        keep_default_na=False,
        na_values=[""],
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    _verificar_arquivos()

    con = conectar()
    try:
        criar_schema(con, SCHEMA)
        total = 0
        for arquivo, tabela in ARQUIVO_PARA_TABELA.items():
            linhas = gravar(con, _ler(arquivo), SCHEMA, tabela)
            total += linhas
            print(f"{SCHEMA}.{tabela}: {_milhar(linhas)} linhas")
        print(f"Total: {_milhar(total)} registros")
    finally:
        con.close()


if __name__ == "__main__":
    main()
