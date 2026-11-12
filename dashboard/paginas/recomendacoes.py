"""5. Recomendações — "O que fazer?"."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import narrativa as nar


def medianas_regionais(ctx: c.Contexto) -> dict[tuple[str, str], float]:
    """Mediana de admissão por mesorregião × macrofamília (referência salarial)."""
    perfil = ctx.art.perfil
    if perfil is None:
        return {}
    if ctx.filtros.escopo == c.ESCOPO_INDUSTRIA:
        perfil = perfil[perfil[c.COLUNA_ESCOPO_INDUSTRIAL]]
    med = c.medianas_perfil(perfil, [c.COLUNA_REGIAO, c.COLUNA_MACROFAMILIA_CBO])
    return {(r, m): v for r, m, v in zip(med[c.COLUNA_REGIAO], med[c.COLUNA_MACROFAMILIA_CBO], med["mediana_admissao"])}


def classificar_prioridade(recs: list[c.Recomendacao]) -> dict[int, str]:
    """Alta/Média/Baixa pelos tercis da prioridade (severidade × volume)."""
    if not recs:
        return {}
    serie = pd.Series([r.prioridade for r in recs])
    q1, q2 = serie.quantile(1 / 3), serie.quantile(2 / 3)
    return {i: ("Alta" if p >= q2 else "Média" if p >= q1 else "Baixa") for i, p in enumerate(serie)}


def ficha_mesorregiao(ctx: c.Contexto, regiao: str, recs: list[c.Recomendacao]) -> str:
    """Ficha em Markdown: diagnóstico + 3 recomendações, só com números calculados."""
    dados = ctx.df[ctx.df[c.COLUNA_REGIAO].astype(str) == regiao]
    t, ref = c.total(dados), c.total(ctx.df)
    m = c.matriz_diagnostico(ctx.df, [c.COLUNA_REGIAO, c.COLUNA_SETOR])
    m = m[m[c.COLUNA_REGIAO].astype(str) == regiao]
    piso = max(c.MIN_MOVIMENTACOES, nar.FRACAO_RELEVANCIA * float(t[c.M_MOV]))
    relevantes = m[m[c.M_MOV] >= piso]
    linhas = [
        f"# Ficha — {regiao}",
        f"*{ctx.filtros.escopo}, {nar.periodo(dados)}. "
        "Gerada pelo painel Raio-X da Indústria SC.*",
        "",
        "## Diagnóstico",
        f"- {c.fmt_int(t[c.M_MOV])} movimentações e saldo de {c.fmt_int(t[c.M_SALDO])} "
        f"({c.fmt_metrica(c.M_SALDO_10K, t[c.M_SALDO_10K])} por 10 mil hab.).",
        f"- Saída voluntária {c.fmt_pct(t[c.M_SAIDA_VOL])} (estado: {c.fmt_pct(ref[c.M_SAIDA_VOL])}); "
        f"gap salarial de reposição {c.fmt_razao(t[c.M_GAP_SAL])} (estado: {c.fmt_razao(ref[c.M_GAP_SAL])}).",
        f"- Gap de escolaridade {c.fmt_metrica(c.M_GAP_ESC, t[c.M_GAP_ESC])} nível(is).",
    ]
    if not m.empty:
        tensa = (relevantes if not relevantes.empty else m).iloc[0]
        linhas.append(f"- Setor mais tenso: **{tensa[c.COLUNA_SETOR]}** ({tensa['quadrante']}; motor: {tensa['motor']}).")
        cont = m["quadrante"].value_counts()
        linhas.append("- Setores por quadrante: " + "; ".join(f"{q}: {n}" for q, n in cont.items()) + ".")
    linhas += ["", "## Recomendações prioritárias"]
    proprias = [r for r in recs if r.regiao == regiao][:3]
    if not proprias:
        linhas.append("- Nenhuma regra disparou com amostra suficiente nesta mesorregião.")
    for i, r in enumerate(proprias, 1):
        linhas += [f"{i}. **{r.alavanca}** — {r.macrofamilia} (nível {r.nivel_alvo})",
                   f"   - Gatilho: {r.regra}.", f"   - Evidência: {r.evidencia}."]
    linhas += ["", "_Fonte: Novo CAGED (MTE), movimentações; macrofamílias por IA com dupla rodada. "
               "O CAGED mede fluxos, não vagas abertas._"]
    return "\n".join(linhas)


def render(ctx: c.Contexto) -> None:
    st.title("O que fazer?")
    c.cabecalho(ctx)
    if ctx.df.empty:
        st.info("Nenhuma movimentação com estes filtros.")
        return
    recs = c.gerar_recomendacoes(ctx.df, mediana_regional=medianas_regionais(ctx))
    prioridades = classificar_prioridade(recs)
    ref = c.total(ctx.df)
    st.markdown(
        f"Cinco regras ligam o diagnóstico de cada **mesorregião × macrofamília (IA)** a uma alavanca da empresa. "
        f"Referência do recorte: saída voluntária {c.fmt_pct(ref[c.M_SAIDA_VOL])}. "
        f"**{len(recs)} recomendações** disparadas."
    )
    if not recs:
        st.info("Nenhuma regra disparou com amostra suficiente (≥ 100 movimentações) nesta seleção.")
    else:
        st.subheader("Prioridades")
        colunas = st.columns(3)
        for i, r in enumerate(recs[:6]):
            with colunas[i % 3].container(border=True, height="stretch"):
                st.markdown(f"**{r.alavanca}**")
                st.markdown(f":material/location_on: {r.regiao} · :material/work: {r.macrofamilia} · nível {r.nivel_alvo}")
                st.markdown(f"Prioridade **{prioridades[i]}** · {c.fmt_int(r.movimentacoes)} movimentações")
                st.caption(f"Gatilho: {r.regra}.")
                st.caption(f"Evidência: {r.evidencia}.")

        st.subheader("Todas as recomendações")
        tabela = pd.DataFrame([{
            "Prioridade": prioridades[i], "Alavanca": r.alavanca, "Mesorregião": r.regiao,
            "Macrofamília (IA)": r.macrofamilia, "Nível-alvo": r.nivel_alvo, "Movimentações": int(r.movimentacoes),
            "Evidência": r.evidencia, "Gatilho": r.regra,
        } for i, r in enumerate(recs)])
        col1, col2 = st.columns(2)
        alavancas = col1.multiselect("Alavanca", sorted(tabela["Alavanca"].unique()), placeholder="Todas")
        regioes = col2.multiselect("Mesorregião", sorted(tabela["Mesorregião"].unique()), placeholder="Todas")
        filtrada = c.aplicar_filtros(tabela, Alavanca=alavancas, **{"Mesorregião": regioes})
        st.dataframe(filtrada, hide_index=True, width="stretch",
                     column_config={"Movimentações": st.column_config.NumberColumn(format="localized")})
        c.baixar_csv(filtrada, "recomendacoes.csv", "Baixar recomendações (CSV)")

    st.subheader("Ficha da mesorregião")
    regioes = sorted(ctx.df[c.COLUNA_REGIAO].astype(str).unique())
    escolhida = st.selectbox("Mesorregião", regioes, key="ficha_meso")
    texto = ficha_mesorregiao(ctx, escolhida, recs)
    with st.container(border=True):
        # Na tela, títulos menores; o arquivo baixado mantém # e ##.
        st.markdown(texto.replace("\n## ", "\n##### ").replace("# Ficha", "#### Ficha", 1))
    st.download_button("Baixar ficha (Markdown)", texto.encode("utf-8"),
                       file_name=f"ficha_{escolhida.lower().replace(' ', '_')}.md", icon=":material/download:")

    st.subheader("Quanto custa a saída voluntária?")
    n = st.slider("Custo de repor um trabalhador, em salários (premissa ajustável)", 1, 12, 3, 1,
                  help="Inclui recrutamento, seleção, treinamento e produtividade perdida até o novo "
                       "contratado render plenamente. É uma premissa: ajuste à realidade da empresa.")
    t = c.total(ctx.df)
    custo = t[c.COLUNA_DESLIGAMENTOS_A_PEDIDO] * t[c.M_SAL_DESL] * n
    col1, col2, col3 = st.columns(3)
    col1.metric("Desligamentos a pedido", c.fmt_int(t[c.COLUNA_DESLIGAMENTOS_A_PEDIDO]), border=True)
    col2.metric("Salário médio de quem sai", c.fmt_brl(t[c.M_SAL_DESL]), border=True)
    col3.metric("Custo estimado de reposição", f"R$ {c.fmt_num(custo / 1e6, 1)} mi", border=True,
                help="desligamentos a pedido × salário médio de desligamento × N salários")
    st.caption("Estimativa de ordem de grandeza para a seleção atual, não um valor contábil.")
