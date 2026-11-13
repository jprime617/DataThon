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
  csv [label="Novo CAGED SC\\n(FTP do MTE, 24 meses:\\nMOV + FOR − EXC)"];
  rais [label="RAIS 2025\\n(estoque em 31/12)"];
  inpc [label="INPC (IBGE)\\ndeflator"];
  mun [label="Municípios SC\\n(IBGE)"];
  limpeza [label="Limpeza e\\ndecodificação"];
  juncao [label="Junção por\\nmunicípio"];
  ia [label="IA: CBO →\\nmacrofamília + nível\\n(2 rodadas)", fillcolor="#FFF1E0", color="#D55E00"];
  agreg [label="Agregação\\n(contagens aditivas,\\nperfil, metadados)"];
  blob [label="Azure Blob\\nStorage", fillcolor="#E0F0FF"];
  app [label="Azure App Service\\n(este painel)", fillcolor="#E0F0FF"];
  csv -> limpeza -> juncao -> ia -> agreg -> blob -> app;
  mun -> juncao;
  inpc -> limpeza;
  rais -> agreg;
  agreg -> app [style=dashed, label="cópia local\\n(fallback)", fontsize=11];
}
"""

LIMITES = """
- **24 meses de dados** (set/24–ago/26), reconstruídos do FTP do MTE como MOV + FOR − EXC e conferidos contra a base fornecida no bloco recente (diferença de +0,02% nas admissões e +0,005% nos desligamentos). O painel abre nos **últimos 12 meses** (o mesmo período da base fornecida); o bloco anterior só alimenta a aceleração.
- **O CAGED mede fluxos, não estoque, e não tem vagas abertas.** "Apagão" é inferido por sinais de tensão (rotatividade descontada, saída voluntária e desligamento precoce; a compressão salarial entra como causa), não observado.
- **Estoque de 31/12/2025 como aproximação do estoque médio.** A rotatividade descontada do MTE divide pelo estoque médio do período; usamos o estoque CLT de SC em 31/12/2025 (RAIS 2025, fonte pública do MTE), que cai no meio da janela set/25–ago/26. Resultado: SC 34,8% contra 33,6% na taxa oficial de out/25–set/26. Células sem movimentação no período ficam fora (≈ 1% do estoque). O antigo "giro" (mín ÷ máx) saiu porque era função exata do saldo relativo.
- **A RAIS só tem o vínculo CLT** (tipos 10–25 e 60–75): aprendizes, temporários e estatutários ficam fora; transferências (motivos 30–34) não contam como desligamento.
- **Salários são declarados pelo empregador** e estão **deflacionados pelo INPC a preços de ago/2026**; as medianas do perfil, ao juntar células, são aproximadas pela mediana ponderada.
- **IDHM é de 2010**; PIB per capita de 2023; população estimada 2026. Correlações territoriais não implicam causalidade.
- **A classificação por IA é uma interpretação**, mitigada por regras explícitas (A–D), conjunto fechado e uma 2ª rodada com a ordem embaralhada.
- **Emprego formal CLT apenas**: informalidade, autônomos e PJ ficam fora.
"""

PROXIMOS = """
- **SC × Brasil** por seção (Tabelas 6.1 e 10 do CAGED) para separar o que é estrutural do que é local.
- Intervalos de confiança por bootstrap; RAIS 2024 e estoque mensal rolado.
"""

# Para a banca: cada requisito (.kiro/specs/.../requirements.md) e onde conferi-lo.
REQUISITOS = [
    ("R1", "Ingestão e validação dos dados de origem",
     "Pipeline (`notebooks/01_pipeline.ipynb`, etapa 1); nesta página, em Procedência e no funil de linhas."),
    ("R2", "Limpeza, tipos e decodificação",
     "Funil desta página (linhas fora do período excluídas); regra de salário válido em Procedência."),
    ("R3", "Cruzamento CAGED × municípios",
     "Saldo por 10 mil hab. (Panorama) e população, IDHM e PIB na Ficha do território."),
    ("R4", "Métricas de negócio",
     "Indicadores do Panorama e tabela Definições desta página; rotatividade descontada no tema Tensão, ao lado da taxa oficial."),
    ("R5", "Agrupamento de CBOs via IA",
     "Página Que profissional falta: macrofamílias, regras A–D, prompt e concordância entre rodadas."),
    ("R6", "Agregações para o painel",
     "Tabelas pré-agregadas lidas pelo painel; botão Baixar dados filtrados (CSV) em cada página."),
    ("R7.1", "No mínimo 3 KPIs",
     "Panorama: coluna Principais (4 indicadores) e Ficha do território."),
    ("R7.2", "Mapa de SC pelo saldo por 10 mil hab.",
     "Panorama: escolha Saldo por 10 mil hab. e Município no mapa (escala divergente, legenda em faixas)."),
    ("R7.3", "Ranking de seções por saldo",
     "Panorama: tabela Seções, com a rotatividade descontada e a saída voluntária ao lado."),
    ("R7.4", "Salário × escolaridade ordinal média",
     "Por que acontece → Aprofundar: qualificação e retenção (dispersão por macrofamília)."),
    ("R7.5–7.6", "Filtros e recorte vazio",
     "Barra lateral (período, território, setor, macrofamília, nível); recorte vazio mostra aviso, sem erro."),
    ("R7.7–7.8", "Leitura das tabelas e falha de dados",
     "Procedência desta página (origem em uso); sem dados, o painel avisa e não desenha os gráficos."),
    ("R8", "Reprodutibilidade e documentação",
     "README, notebook do pipeline, testes automatizados e commit do pipeline em Procedência."),
    ("R9", "Implantação no Azure",
     "Este painel no Azure App Service, lendo do Azure Blob Storage (origem em Procedência)."),
]


def _sensibilidade(ctx: c.Contexto) -> None:
    """Robustez do índice de tensão (veio de Quem precisa de atenção no M3.C8)."""
    if len(c.PESOS_TENSAO_PADRAO) < 2 or ctx.df.empty:
        return
    with st.expander("Sensibilidade: o top 10 de tensão muda com outros pesos?"):
        por = [c.COLUNA_REGIAO, c.COLUNA_SETOR]
        m = c.matriz_diagnostico(ctx.df, por)
        st.caption("Unidade: mesorregião × setor. Pesos iniciais iguais (PLANEJAMENTO §7.1). Mude-os e veja quantas "
                   "unidades permanecem no top 10 de tensão.")
        cols = st.columns(len(c.PESOS_TENSAO_PADRAO))
        pesos = {nome: col.slider(f"Peso: {c.ROTULO_COMPONENTE[nome]}", 0.0, 3.0, 1.0, 0.5)
                 for col, nome in zip(cols, c.PESOS_TENSAO_PADRAO)}
        if sum(pesos.values()) == 0:
            st.warning("Ao menos um peso precisa ser maior que zero.")
            return
        alt = c.matriz_diagnostico(ctx.df, por, pesos_tensao=pesos)
        rotulo = lambda d: list((d[c.COLUNA_SETOR].astype(str) + " – " + d[c.COLUNA_REGIAO].astype(str)).head(10))
        base10, alt10 = rotulo(m), rotulo(alt)
        st.markdown(f"**{len(set(base10) & set(alt10))} de {min(10, len(base10))}** unidades permanecem no top 10.")
        st.dataframe(pd.DataFrame({"Pesos iguais": pd.Series(base10), "Pesos escolhidos": pd.Series(alt10)},
                                  index=range(1, max(len(base10), len(alt10)) + 1)), width="stretch")


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
        "- **Dinamismo** = média dos z-scores da **variação do emprego** (saldo ÷ estoque de 31/12/2025) e da **aceleração** "
        "(saldo de set/25–ago/26 menos o de set/24–ago/25, ÷ estoque), entre as unidades com amostra. Blocos de 12 "
        "meses comparam o mesmo calendário, sem sazonalidade.\n"
        "- **Tensão** = média dos z-scores dos três **sintomas** de dificuldade de reter gente, com pesos iguais: "
        "**rotatividade descontada**, **saída voluntária** e **desligamento precoce** (< 12 meses de casa). "
        "O expander abaixo mostra se o top 10 muda com outros pesos.\n"
        "- **Causas não entram no índice.** A compressão salarial (gap < 0,95), o gap de escolaridade e a retenção "
        "viram selos em Quem precisa de atenção e regras em O que fazer. Somá-las à tensão e depois usá-las para explicá-la "
        "seria contar a mesma coisa duas vezes.\n"
        "- **Saíram:** o giro (função exata do saldo relativo) e a aceleração entre semestres (media o calendário: "
        "dezembro concentra desligamentos); ela voltou na forma de blocos de 12 meses."
    )

    _sensibilidade(ctx)

    st.subheader("Requisitos do desafio: onde conferir")
    st.table(pd.DataFrame(REQUISITOS, columns=["Requisito", "O quê", "Onde aparece"]).set_index("Requisito"))

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
