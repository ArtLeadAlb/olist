"""Relatório HTML do painel Olist: um arquivo só, para abrir com dois cliques.

Execução:
    uv run python relatorio.py

A spec do painel (docstring de painel.py) continua valendo. Esta é a do
relatório.

SPEC (e o porquê de cada regra)

1. Lê os marts com painel.ler(), formata com painel.reais/pct/numero e monta
   os gráficos com as mesmas funções de painel.py. Não importa streamlit.
   Não desenha nenhum gráfico que não esteja em painel.py.
   Por quê: um número ou um gráfico que existe no relatório e não no painel
   (ou o contrário) é duas versões da verdade. Sem streamlit, porque o
   relatório roda onde ninguém instalou a página.

2. Escreve relatorio.html na raiz: um arquivo só, com as mesmas quatro
   faixas do app.py, na mesma ordem. Cartões em HTML simples, numa grade.
   Gráficos com figura.to_html(full_html=False); a biblioteca do plotly vem
   do CDN uma vez só, no primeiro gráfico (include_plotlyjs="cdn"), e nos
   outros include_plotlyjs=False. Cada gráfico com div_id fixo ("g01",
   "g02"...).
   Por quê: sem div_id o plotly sorteia um id novo a cada execução, e o
   arquivo muda sem o dado mudar. A biblioteca uma vez só mantém o arquivo
   pequeno.

3. Sem filtro: o faturamento mostra o mesmo período padrão do app.py,
   jan/2017 a ago/2018, e o título diz o período.
   Por quê: sem filtro, quem lê não tem como saber o recorte se o título
   não disser.

4. Rodapé com a data e a hora em que o arquivo foi gerado:
   "Dados de 25/10/2026 14:03".
   Por quê: o arquivo não fala com o banco; quem lê precisa saber de quando
   é o número.

5. Imprime o caminho do arquivo e o tamanho em KB. stdout em utf-8.
   Por quê: o tamanho é o instrumento de conferência do critério de 200 KB,
   e o Prompt de Comando do Windows embaralha acento por padrão.

CRITÉRIOS DE ACEITE
- Abrir relatorio.html com dois cliques mostra os sete cartões com os mesmos
  valores do app.py.
- O arquivo tem menos de 200 KB.
- Rodar duas vezes muda só a data do rodapé.
"""

import html
import sys
from datetime import datetime
from pathlib import Path

import painel

# Os mesmos marts de app.py. Não dá para importar a lista de lá: app.py
# importa streamlit, e este arquivo não pode.
MARTS = (
    "kpis", "recompra", "entrega_no_prazo", "vendas_mensais",
    "top_categorias", "mix_pagamento", "ticket_medio_por_estado",
    "clientes_por_uf", "nota_por_categoria", "vendedores_pareto",
)

COMANDO = "uv run python -m pipeline.marts"
ARQUIVO = Path(__file__).resolve().parent / "relatorio.html"

CSS = """
body { font-family: system-ui, sans-serif; margin: 0 auto; padding: 1rem 1.5rem; max-width: 1800px; color: #222; }
h1 { font-size: 1.8rem; margin: 0.5rem 0 1rem; }
.cartoes { display: grid; grid-template-columns: repeat(7, 1fr); gap: 0.75rem; margin-bottom: 1rem; }
.cartao { border: 1px solid #ddd; border-radius: 8px; padding: 0.75rem; }
.rotulo { font-size: 0.8rem; color: #555; }
.valor { font-size: 1.6rem; font-weight: 600; margin-top: 0.25rem; }
.largo { margin-bottom: 1rem; }
.tres { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1rem; }
footer { color: #666; font-size: 0.85rem; margin-top: 1.5rem; border-top: 1px solid #ddd; padding-top: 0.75rem; }
@media (max-width: 1100px) {
  .cartoes { grid-template-columns: repeat(2, 1fr); }
  .tres { grid-template-columns: 1fr; }
}
"""


def _erro(mensagem: str) -> None:
    print(mensagem, file=sys.stderr)
    sys.exit(1)


def _cartoes(dados: dict) -> list[tuple[str, str]]:
    # Mesmos rótulos, valores e casas decimais de app.py.
    kpis = dados["kpis"].iloc[0]
    no_prazo = dados["entrega_no_prazo"].iloc[0]
    return [
        ("Ticket médio · por pedido", painel.reais(kpis["ticket_medio"])),
        ("Cancelados · % de todos os pedidos", painel.pct(kpis["pct_cancelados"], 2)),
        ("Peso do frete · % do valor pago", painel.pct(kpis["pct_frete"], 1)),
        ("Recompra · % com 2+ pedidos", painel.pct(painel.pct_recompra(dados["recompra"]), 2)),
        ("No prazo · % até a data prevista", painel.pct(no_prazo["pct_no_prazo"], 1)),
        ("Dias até entregar · da compra", painel.numero(kpis["dias_entrega"], 1)),
        ("Nota média · de 1 a 5", painel.numero(kpis["nota_media"], 2)),
    ]


def _figuras(dados: dict) -> list:
    """As sete figuras, na ordem em que aparecem na página (g01 a g07)."""
    lista_meses = painel.meses(dados["vendas_mensais"])
    inicio, fim = painel.periodo_padrao(lista_meses)
    recorte = painel.recortar_periodo(dados["vendas_mensais"], inicio, fim)

    faturamento = painel.grafico_faturamento(recorte)
    faturamento.update_layout(
        title=f"01 · Faturamento mensal · {painel.mes_rotulo(inicio)} a {painel.mes_rotulo(fim)}"
    )
    return [
        faturamento,
        painel.grafico_categorias(dados["top_categorias"]),
        painel.grafico_pagamento(dados["mix_pagamento"]),
        painel.grafico_ticket_uf(dados["ticket_medio_por_estado"]),
        painel.grafico_clientes_uf(dados["clientes_por_uf"]),
        painel.grafico_nota_categoria(dados["nota_por_categoria"]),
        painel.grafico_vendedores(dados["vendedores_pareto"]),
    ]


def _divs(figuras: list) -> list[str]:
    return [
        figura.to_html(
            full_html=False,
            include_plotlyjs="cdn" if i == 1 else False,  # a biblioteca, uma vez só
            div_id=f"g{i:02d}",  # fixo: sem ele o id muda a cada execução
        )
        for i, figura in enumerate(figuras, start=1)
    ]


def _documento(cartoes: list, divs: list[str], gerado_em: datetime) -> str:
    html_cartoes = "".join(
        f'<div class="cartao"><div class="rotulo">{html.escape(rotulo)}</div>'
        f'<div class="valor">{html.escape(valor)}</div></div>'
        for rotulo, valor in cartoes
    )
    faixa3 = "".join(f"<div>{d}</div>" for d in divs[1:4])
    faixa4 = "".join(f"<div>{d}</div>" for d in divs[4:7])
    titulo = "Olist · visão da operação"
    return (
        '<!DOCTYPE html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{titulo}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f"<h1>{titulo}</h1>\n"
        f'<section class="cartoes">{html_cartoes}</section>\n'
        f'<section class="largo">{divs[0]}</section>\n'
        f'<section class="tres">{faixa3}</section>\n'
        f'<section class="tres">{faixa4}</section>\n'
        f"<footer>Dados de {gerado_em:%d/%m/%Y %H:%M}</footer>\n"
        "</body>\n</html>\n"
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    try:
        dados = painel.ler(list(MARTS))
    except painel.BancoAusente as e:
        _erro(f"Banco não encontrado: {e}. Gere os marts com: {COMANDO}")
    except painel.MartsAusentes as e:
        _erro(f"Marts ausentes: {', '.join(e.nomes)}. Gere-os com: {COMANDO}")

    documento = _documento(_cartoes(dados), _divs(_figuras(dados)), datetime.now())
    # write_bytes: as quebras de linha ficam iguais em qualquer sistema.
    ARQUIVO.write_bytes(documento.encode("utf-8"))

    kb = ARQUIVO.stat().st_size / 1024
    print(f"Relatório gerado: {ARQUIVO} ({painel.numero(kb, 1)} KB)")


if __name__ == "__main__":
    main()
