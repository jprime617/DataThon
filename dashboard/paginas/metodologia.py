"""7. Metodologia e sistema — de onde vêm os números e quais são os limites."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig

ARQUITETURA = """
digraph {
  rankdir=TB; bgcolor="transparent"; nodesep=0.4; ranksep=0.35;
  node [shape=box, style="rounded,filled", fillcolor="#E8F0F8", color="#0F4C81", fontname="Helvetica", fontsize=15, width=3];
  edge [color="#555555"];
  csv [label="Novo CAGED SC\\n(CSV, 12 meses)"];
  mun [label="Municípios SC\\n(IBGE)"];
  limpeza [label="Limpeza e\\ndecodificação"];
  juncao [label="Junção por\\nmunicípio"];
  ia [label="IA: CBO →\\nmacrofamília + nível\\n(2 rodadas)", fillcolor="#FFF1E0", color="#D55E00"];
  agreg [label="Agregação\\n(contagens aditivas,\\nperfil, metadados)"];
  blob [label="Azure Blob\\nStorage", fillcolor="#E0F0FF"];
  app [label="Azure App Service\\n(este painel)", fillcolor="#E0F0FF"];
  csv -> limpeza -> juncao -> ia -> agreg -> blob -> app;
  mun -> juncao;
  agreg -> app [style=dashed, label="cópia local\\n(fallback)", fontsize=11];
}
"""

LIMITES = """
- **12 meses de dados** (set/25–ago/26): sem um bloco anterior de 12 meses, não há aceleração sem sazonalidade, então ela fica fora do índice.
- **O CAGED mede fluxos, não estoque, e não tem vagas abertas.** "Apagão" é inferido por sinais de tensão (hoje, a saída voluntária; a compressão salarial entra como causa), não observado.
- **Sem estoque de vínculos não há taxa de rotatividade.** O antigo "giro" (mín ÷ máx entre admissões e desligamentos) saiu porque era função exata do saldo relativo; a rotatividade descontada do MTE volta com a RAIS.
- **Salários são declarados pelo empregador** e não deflacionados; as medianas do perfil, ao juntar células, são aproximadas pela mediana ponderada.
- **IDHM é de 2010**; PIB per capita de 2023; população estimada 2026. Correlações territoriais não implicam causalidade.
- **A classificação por IA é uma interpretação**, mitigada por regras explícitas (A–D), conjunto fechado e uma 2ª rodada com a ordem embaralhada.
- **Emprego formal CLT apenas**: informalidade, autônomos e PJ ficam fora.
"""

PROXIMOS = """
- Estoque de vínculos (RAIS 2025) para a **rotatividade descontada** e mais dois sintomas no índice de Tensão.
- **Janela de 24 meses** (MOV + FOR − EXC do FTP do MTE) para a aceleração por blocos de 12 meses, sem sazonalidade.
- **SC × Brasil** por seção (Tabelas 6.1 e 10 do CAGED) para separar o que é estrutural do que é local.
- **Desligamento precoce** (< 12 meses de casa), que exige a RAIS.
- Salários deflacionados pelo INPC e intervalos de confiança por bootstrap.
"""


def render(ctx: c.Contexto) -> None:
    st.title("Metodologia e sistema")
    c.cabecalho(ctx)
    meta = ctx.art.metadados or {}

    st.subheader("Arquitetura")
    _, centro, _ = st.columns([1, 2, 1])
    centro.graphviz_chart(ARQUITETURA, width="stretch")
    st.caption("O LLM roda só no pipeline local; o painel lê tabelas pré-agregadas de poucos MB, nunca microdados.")

    st.subheader("Procedência dos dados")
    linhas = meta.get("linhas", {})
    periodo = meta.get("periodo", {})
    st.markdown(
        f"- **Origem em uso:** {({'blob': 'Azure Blob Storage', 'local': 'cópia local do pacote'}).get(ctx.art.origem, '—')}\n"
        f"- **Gerado em:** {str(meta.get('gerado_em', '—'))[:16].replace('T', ' ')} · **commit do pipeline:** "
        f"`{meta.get('commit') or '—'}`\n"
        f"- **Período:** {c.rotulo_mes(periodo.get('inicio', ''))}–{c.rotulo_mes(periodo.get('fim', ''))} "
        f"({periodo.get('meses', '—')} meses)\n"
        + (f"- **Salário válido:** {meta['salario_valido']['regra']} (teto {c.fmt_brl(meta['salario_valido']['teto'])})"
           if meta.get("salario_valido", {}).get("teto") else "")
    )
    for aviso in ctx.art.avisos:
        st.caption(f":material/info: {aviso}")

    if linhas:
        etapas = [("Linhas no arquivo bruto", linhas.get("brutas", 0)),
                  ("Após filtro de competência", linhas.get("apos_limpeza", 0)),
                  ("Movimentações agregadas", linhas.get("movimentacoes_agregadas", 0)),
                  ("Indústria (seções B–F)", linhas.get("movimentacoes_industria", 0))]
        st.plotly_chart(fig.construir_funil(etapas), width="stretch")
        st.caption(f"{c.fmt_int(linhas.get('excluidas_competencia', 0))} linhas fora do período foram excluídas. "
                   f"Agregado: {c.fmt_int(linhas.get('agregado', 0))} linhas; perfil: "
                   f"{c.fmt_int(linhas.get('perfil', 0))} linhas.")

    st.subheader("Definições")
    st.table(pd.DataFrame([{"Indicador": d.rotulo, "Fórmula": d.formula} for d in c.DEFINICOES.values()])
             .set_index("Indicador"))
    st.caption(f"Guarda de amostra: taxas exigem ≥ {c.MIN_MOVIMENTACOES} movimentações; gaps salariais, "
               f"≥ {c.MIN_SALARIOS} salários de admissão e de desligamento. Abaixo disso a célula fica em cinza "
               "e sai de rankings e da matriz.")

    st.subheader("Índice: Tensão = sintomas; causas ficam no diagnóstico")
    st.markdown(
        "- **Dinamismo** = z-score do saldo relativo (saldo ÷ movimentações) entre as unidades com amostra.\n"
        "- **Tensão** = média ponderada dos z-scores dos **sintomas** de dificuldade de reter gente. Hoje há um só: "
        "a **saída voluntária**. Rotatividade descontada e desligamento precoce entram quando houver o estoque da RAIS.\n"
        "- **Causas não entram no índice.** A compressão salarial (gap < 0,95), o gap de escolaridade e a retenção "
        "viram selos no Diagnóstico e regras nas Recomendações. Somá-las à tensão e depois usá-las para explicá-la "
        "seria contar a mesma coisa duas vezes.\n"
        "- **Saíram:** o giro (função exata do saldo relativo) e a aceleração entre semestres (media o calendário: "
        "dezembro concentra desligamentos)."
    )

    st.subheader("Premissas e limites")
    st.markdown(LIMITES)

    st.subheader("Qualidade do código")
    testes = meta.get("testes")
    repo = os.environ.get("DASHBOARD_REPO_URL", "").strip()
    st.markdown(
        (f"- **{testes} testes automatizados** (pytest + Hypothesis) cobrindo pipeline, métricas, regras e páginas.\n"
         if testes else "")
        + f"- Código-fonte: {f'[{repo}]({repo})' if repo else 'repositório Git do projeto'}"
        + (f" (commit `{meta.get('commit')}`)." if meta.get("commit") else ".")
    )

    st.subheader("Próximos passos")
    st.markdown(PROXIMOS)
