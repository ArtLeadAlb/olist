🛒 Olist E-commerce Analytics | Engenharia de Dados & Análise de Dados

Do dado bruto ao dashboard: uma solução completa de Engenharia e Análise de Dados utilizando o dataset público da Olist.

📌 Sobre o projeto

Este projeto tem como objetivo desenvolver uma solução completa de dados a partir do Brazilian E-Commerce Public Dataset by Olist, disponibilizado no Kaggle.

A proposta foi construir um fluxo de trabalho que percorresse todas as etapas de um projeto de dados, desde a ingestão dos arquivos originais até a transformação, organização, modelagem analítica e disponibilização das informações em um dashboard interativo.

Mais do que realizar uma análise exploratória, o projeto busca aplicar conceitos de Engenharia de Dados e Analytics Engineering em um cenário próximo de uma necessidade real de negócio.

🎯 Objetivos
Desenvolver um pipeline de ETL para processamento dos dados da Olist.
Estruturar e armazenar os dados utilizando DuckDB.
Aplicar transformações e consultas analíticas com SQL.
Organizar os dados em modelos voltados à análise.
Desenvolver visualizações para facilitar a interpretação dos indicadores.
Disponibilizar os resultados por meio de um dashboard interativo.
Aplicar boas práticas de organização, testes e qualidade de código.
📊 Fonte dos dados

O projeto utiliza o conjunto de dados público da Olist, disponibilizado no Kaggle:

Brazilian E-Commerce Public Dataset by Olist

https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

O dataset reúne informações sobre o ecossistema de comércio eletrônico brasileiro, incluindo dados relacionados a:

Pedidos e status das compras.
Clientes e localização geográfica.
Produtos e categorias.
Vendedores.
Pagamentos e formas de pagamento.
Avaliações dos consumidores.
Itens dos pedidos.
Informações geográficas.

Essas informações permitem explorar diferentes perspectivas do negócio, como comportamento de vendas, desempenho operacional, logística e experiência dos consumidores.

🏗️ Arquitetura da solução

O projeto foi organizado para separar as responsabilidades de processamento, transformação e visualização dos dados.

mermaid
flowchart TD
    A["Kaggle - Dataset Olist"] --> B["Dados brutos CSV"]
    B --> C["Pipeline de ingestão"]
    C --> D["DuckDB"]
    D --> E["Transformações SQL"]
    E --> F["SQL Marts"]
    F --> G["Camada analítica"]
    G --> H["Dashboard interativo"]

Etapas do processamento

1. Ingestão dos dados

Leitura dos arquivos disponibilizados pelo Kaggle e carregamento das informações para o ambiente de processamento.

2. Armazenamento

Utilização do DuckDB como mecanismo de armazenamento e consulta analítica dos dados.

3. Transformação e modelagem

Aplicação de consultas SQL para organizar e preparar os dados para análises, mantendo uma separação entre o processamento e os modelos analíticos.

4. Análise de dados

Exploração das informações e construção de indicadores para investigar diferentes aspectos do comércio eletrônico.

5. Visualização

Disponibilização dos resultados por meio de um dashboard interativo, utilizando recursos de visualização de dados.

🛠️ Tecnologias utilizadas
Tecnologia	Aplicação
Python	Desenvolvimento do pipeline e processamento
DuckDB	Banco de dados analítico
SQL	Consultas e transformações
Pandas	Manipulação de dados
Plotly	Visualizações interativas
Streamlit	Desenvolvimento do dashboard
Pytest	Testes automatizados
Ruff	Padronização e análise de código
uv	Gerenciamento do ambiente e dependências
📁 Estrutura do projeto
text
olist/
│
├── pipeline/
│   └── # Scripts de ingestão e processamento
