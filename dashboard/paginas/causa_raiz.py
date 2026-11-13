"""3. Causa raiz — "Por quê: salário, qualificação ou estrutura?"."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar
from src.mapeamentos import FAIXAS_ESCOLARIDADE

ORDEM_FAIXAS = [rotulo for _, rotulo in FAIXAS_ESCOLARIDADE]


def perfil_filtrado(ctx: c.Contexto) -> tuple[pd.DataFrame | None, str]:
    """Recorta o perfil (mesorregião × setor × macrofamília × nível × faixa).

    O perfil não tem município nem mês: uma seleção de micro/município usa as
    mesorregiões que a contêm, e o período é sempre o inteiro.
    """
    perfil = ctx.art.perfil
    if perfil is None:
        return None, ""
    f = ctx.filtros
    nota = "Medianas do período inteiro"
    regioes: list[str] = []
    if f.territorios:
        regioes = sorted(ctx.df[c.COLUNA_REGIAO].astype(str).unique())
        if f.nivel_territorial != c.NIVEL_MESO:
            nota += f", pela(s) mesorregião(ões) da seleção: {', '.join(regioes)}"
    sel = perfil
    sel = sel[c.mascara_escopo(sel, f.escopo)]
    sel = c.aplicar_filtros(sel, regiao=regioes, **{c.COLUNA_SETOR: f.setores,
                                                    c.COLUNA_MACROFAMILIA_CBO: f.macrofamilias,
                                                    c.COLUNA_NIVEL_QUALIFICACAO: f.niveis})
    return sel, nota + ". Ao juntar células, a mediana é a mediana das medianas ponderada pelo número de salários."


def legenda_compressao(medianas: pd.DataFrame, categoria: str) -> str:
    dados = medianas[(medianas["n_admissao"] >= c.MIN_SALARIOS) & (medianas["n_desligamento"] >= c.MIN_SALARIOS)].copy()
    if dados.empty:
        return ""
    dados["razao"] = dados["mediana_admissao"] / dados["mediana_desligamento"]
    pior = dados.loc[dados["razao"].idxmin()]
    return (f"Maior compressão em **{pior[categoria]}**: a mediana de quem entra é "
            f"{c.fmt_pct(pior['razao'], 0)} da de quem sai ({c.fmt_brl(pior['mediana_admissao'])} vs "
            f"{c.fmt_brl(pior['mediana_desligamento'])}).")


LEGENDA_CAUSAS = ("Salarial = quem entra ganha mais de 5% menos que quem saiu; Qualificação = entra gente menos "
                  "escolarizada numa área técnica; Retenção = muito mais gente pede para sair do que no estado, "
                  "sem que o salário de entrada seja menor.")


def selos_por_unidade(ctx: c.Contexto, unidades: pd.DataFrame) -> pd.DataFrame:
    """Mesorregião × setor com ao menos uma causa (Salarial, Qualificação, Retenção), da maior para a menor."""
    ref = c.total(ctx.df)
    frac = c.fracao_por_nivel(ctx.df, [c.COLUNA_REGIAO, c.COLUNA_SETOR], c.NIVEIS_QUALIFICADOS)
    linhas = []
    for _, u in unidades.iterrows():
        selos = c.causas(u, saida_ref=ref[c.M_SAIDA_VOL],
                         fracao_tecnica=float(frac.get((u[c.COLUNA_REGIAO], u[c.COLUNA_SETOR]), 0.0)))
        if selos:
            linhas.append({"Grupo": f"{u[c.COLUNA_SETOR]} – {u[c.COLUNA_REGIAO]}", "Causas": " · ".join(selos),
                           "Movimentações": int(u[c.M_MOV]),
                           "Salário de quem entra vs quem saiu": c.fmt_gap(u[c.M_GAP_SAL]),
                           "Saem a pedido": c.fmt_pct(u[c.M_SAIDA_VOL])})
    if not linhas:
        return pd.DataFrame(columns=["Grupo", "Causas", "Movimentações"])
    return pd.DataFrame(linhas).sort_values("Movimentações", ascending=False)


def resumo_causas(selos: pd.DataFrame, total: int) -> str:
    """Quantos grupos têm cada causa, em linguagem leiga."""
    if selos.empty:
        return f"Nenhum dos {total} grupos analisados tem uma causa clara nos dados."
    textos = {c.CAUSA_SALARIAL: "o salário de entrada é menor que o de quem saiu",
              c.CAUSA_RETENCAO: "o problema é reter (o salário não é menor)",
              c.CAUSA_QUALIFICACAO: "entra gente com menos estudo numa área técnica"}
    linhas = [f"- **{selos['Causas'].str.contains(causa).sum()}** grupos: {texto}"
              for causa, texto in textos.items() if selos["Causas"].str.contains(causa).any()]
    return (f"Dos {total} grupos (setor × mesorregião) analisados:\n\n" + "\n".join(linhas)
            + "\n\nUm grupo pode ter mais de uma causa.")


def render(ctx: c.Contexto) -> None:
    st.title("Por quê: salário, qualificação ou estrutura?")
    c.cabecalho(ctx)
    if ctx.df.empty:
        st.info("Nenhuma movimentação com estes filtros.")
        return
    c.cartoes_kpi(ctx, [c.M_GAP_SAL, c.M_SAL_ADM, c.M_SAL_DESL, c.M_GAP_ESC, c.M_SAIDA_VOL])

    perfil, nota = perfil_filtrado(ctx)
    unidades = c.agregar_metricas(ctx.df, [c.COLUNA_REGIAO, c.COLUNA_SETOR])
    unidades = unidades[unidades[c.M_AMOSTRA_OK]]
    selos = selos_por_unidade(ctx, unidades)

    st.subheader("Salário: quem entra ganha menos do que quem sai?")
    grafico, resumo = st.columns([3, 2], gap="large")
    por_macro = None
    if perfil is None or perfil.empty:
        grafico.info("Perfil de causa raiz indisponível para esta seleção.")
    else:
        por_faixa = c.medianas_perfil(perfil, [c.COLUNA_FAIXA_ESCOLARIDADE])
        por_faixa = por_faixa.set_index(c.COLUNA_FAIXA_ESCOLARIDADE).reindex(
            [f for f in ORDEM_FAIXAS if f in set(por_faixa[c.COLUNA_FAIXA_ESCOLARIDADE])]).reset_index()
        grafico.plotly_chart(fig.construir_salario_por_categoria(
            por_faixa, c.COLUNA_FAIXA_ESCOLARIDADE, "Mediana salarial por escolaridade"), width="stretch")
        grafico.caption(legenda_compressao(por_faixa, c.COLUNA_FAIXA_ESCOLARIDADE) + " " + nota)
        por_macro = c.medianas_perfil(perfil, [c.COLUNA_MACROFAMILIA_CBO])
    with resumo, st.container(border=True):
        st.markdown("**O que explica a perda de gente**")
        st.markdown(resumo_causas(selos, len(unidades)))

    # No máximo 2 gráficos à vista (M3.C4): o resto fica em "Aprofundar".
    if por_macro is not None:
        with st.expander("Aprofundar: salário por profissão (macrofamília da IA)"):
            st.plotly_chart(fig.construir_salario_por_categoria(
                por_macro, c.COLUNA_MACROFAMILIA_CBO, "Mediana salarial por macrofamília (IA)"), width="stretch")
            st.caption(legenda_compressao(por_macro, c.COLUNA_MACROFAMILIA_CBO))
    with st.expander("Aprofundar: qualificação e retenção"):
        col1, col2 = st.columns(2)
        macros = c.agregar_metricas(ctx.df, [c.COLUNA_MACROFAMILIA_CBO])
        macros = macros[macros[c.COLUNA_MACROFAMILIA_CBO].astype(str) != c.NAO_CLASSIFICADO]
        col1.plotly_chart(fig.construir_gap_escolaridade(macros, c.COLUNA_MACROFAMILIA_CBO), width="stretch")
        nota_esc = nar.destaque_escolaridade(ctx.df, perfil)
        if nota_esc:
            col1.caption(nota_esc)
        rot = unidades[c.COLUNA_SETOR].astype(str) + " – " + unidades[c.COLUNA_REGIAO].astype(str)
        col2.plotly_chart(fig.construir_dispersao(unidades, rot, c.M_GAP_SAL, c.M_SAIDA_VOL,
                                                  "Salário explica a saída voluntária?"), width="stretch")
        validas = unidades.dropna(subset=[c.M_GAP_SAL, c.M_SAIDA_VOL])
        if len(validas) >= 3:
            r = validas[c.M_GAP_SAL].corr(validas[c.M_SAIDA_VOL])
            col2.caption(f"Correlação entre a diferença salarial (entrada vs saída) e a saída voluntária: "
                         f"{c.fmt_num(r, 2)} ({len(validas)} mesorregião × setor com amostra). "
                         "Correlação não é causalidade.")
        # R7.4: salário médio de admissão × escolaridade ordinal média, por macrofamília.
        por_macro = macros[macros[c.M_SALARIO_OK]]
        st.plotly_chart(fig.construir_dispersao(por_macro, por_macro[c.COLUNA_MACROFAMILIA_CBO].astype(str),
                                                c.M_ESC_ADM, c.M_SAL_ADM,
                                                "Quem entra com mais estudo ganha mais? (por macrofamília)"),
                        width="stretch")
        st.caption("Cada bolha é uma macrofamília (IA); o tamanho é o volume de movimentações. "
                   f"Só macrofamílias com ≥ {c.MIN_SALARIOS} salários de cada lado.")

    with st.expander("Aprofundar: riqueza do município (IDHM e PIB per capita)"):
        col1, col2 = st.columns([1, 3])
        eixo_x = col1.radio("Indicador do município", [c.COLUNA_IDHM_2010, c.COLUNA_PIB_PER_CAPITA_2023],
                            format_func={c.COLUNA_IDHM_2010: "IDHM 2010",
                                         c.COLUNA_PIB_PER_CAPITA_2023: "PIB per capita 2023"}.get)
        eixo_y = col1.radio("Sintoma", [c.M_SAIDA_VOL, c.M_GAP_SAL, c.M_SALDO_10K],
                            format_func=lambda m: c.DEFINICOES[m].rotulo)
        municipios = c.agregar_metricas(ctx.df, [c.COLUNA_NOME_MUNICIPIO])
        contexto = ctx.df[[c.COLUNA_NOME_MUNICIPIO, eixo_x]].drop_duplicates(c.COLUNA_NOME_MUNICIPIO)
        municipios = municipios.merge(contexto, on=c.COLUNA_NOME_MUNICIPIO, how="left")
        municipios = municipios[municipios[c.M_AMOSTRA_OK]]
        col2.plotly_chart(fig.construir_dispersao(municipios, municipios[c.COLUNA_NOME_MUNICIPIO], eixo_x, eixo_y,
                                                  "Municípios mais ricos têm menos tensão?"), width="stretch")
        validas = municipios.dropna(subset=[eixo_x, eixo_y])
        if len(validas) >= 3:
            col2.caption(f"Correlação: {c.fmt_num(validas[eixo_x].corr(validas[eixo_y]), 2)} entre "
                         f"{len(validas)} municípios com ≥ 100 movimentações. Correlação não é causalidade; "
                         "o IDHM é de 2010.")

    with st.expander(f"Ver os {len(selos)} grupos com causa identificada"):
        if selos.empty:
            st.caption("Nenhum grupo com causa identificada nesta seleção.")
        else:
            st.dataframe(selos, hide_index=True, width="stretch",
                         column_config={"Movimentações": st.column_config.NumberColumn(format="localized")})
            st.caption(LEGENDA_CAUSAS)
