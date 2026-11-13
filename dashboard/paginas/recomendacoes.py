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


# Por que cada ação aparece, em linguagem leiga.
POR_QUE_ALAVANCA = {
    c.ALAVANCA_SALARIO: "Quem entra ganha menos do que quem saiu, e muita gente pede para sair.",
    c.ALAVANCA_FORMACAO: "Falta gente com formação técnica para as vagas que giram.",
    c.ALAVANCA_MOBILIDADE: "A mesma profissão sobra numa região e falta em outra.",
    c.ALAVANCA_AUTOMACAO: "Muitos postos de nível básico, e o emprego não cresce.",
    c.ALAVANCA_RETENCAO: "Saem muitos a pedido mesmo sem salário menor: o problema não é só dinheiro.",
}


def agrupar_por_alavanca(recs: list[c.Recomendacao]) -> dict[str, list[c.Recomendacao]]:
    """Recomendações por alavanca, na ordem de prioridade da primeira de cada grupo."""
    grupos: dict[str, list[c.Recomendacao]] = {}
    for r in recs:
        grupos.setdefault(r.alavanca, []).append(r)
    return grupos


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
        f"quem entra ganha {c.fmt_gap(t[c.M_GAP_SAL])} do salário de quem saiu (estado: {c.fmt_gap(ref[c.M_GAP_SAL])}).",
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
        "Cada problema encontrado no diagnóstico aponta para uma **ação** que a empresa pode tomar. "
        f"Ao todo, **{len(recs)} recomendações**, agrupadas abaixo por ação."
    )
    if not recs:
        st.info("Nenhuma regra disparou com dados suficientes nesta seleção.")
    else:
        st.subheader("Prioridades")
        grupos = agrupar_por_alavanca(recs)
        colunas = st.columns(min(3, len(grupos)))
        for i, (alavanca, itens) in enumerate(grupos.items()):
            with colunas[i % len(colunas)].container(border=True, height="stretch"):
                st.markdown(f"**{alavanca}**")
                st.caption(POR_QUE_ALAVANCA.get(alavanca, ""))
                st.markdown("\n".join(f"- {r.macrofamilia} · {r.regiao}" for r in itens[:3])
                            + (f"\n\n…e mais {len(itens) - 3}" if len(itens) > 3 else ""))
                st.markdown(f"**{len(itens)}** {'recomendação' if len(itens) == 1 else 'recomendações'} · "
                            f"{c.fmt_int(sum(r.movimentacoes for r in itens))} movimentações")

        tabela = pd.DataFrame([{
            "Prioridade": prioridades[i], "Alavanca": r.alavanca, "Mesorregião": r.regiao,
            "Macrofamília (IA)": r.macrofamilia, "Nível-alvo": r.nivel_alvo, "Movimentações": int(r.movimentacoes),
            "Evidência": r.evidencia, "Gatilho": r.regra,
        } for i, r in enumerate(recs)])
        with st.expander(f"Ver as {len(recs)} recomendações numa tabela (com a evidência de cada uma)"):
            col1, col2 = st.columns(2)
            alavancas = col1.multiselect("Alavanca", sorted(tabela["Alavanca"].unique()), placeholder="Todas")
            regioes = col2.multiselect("Mesorregião", sorted(tabela["Mesorregião"].unique()), placeholder="Todas")
            filtrada = c.aplicar_filtros(tabela, Alavanca=alavancas, **{"Mesorregião": regioes})
            st.dataframe(filtrada, hide_index=True, width="stretch",
                         column_config={"Movimentações": st.column_config.NumberColumn(format="localized")})
            c.baixar_csv(filtrada, "recomendacoes.csv", "Baixar recomendações (CSV)")

    with st.expander("Baixar a ficha de uma mesorregião (texto para levar à reunião)"):
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
    col3.metric("Custo estimado de reposição", c.fmt_brl_escala(custo), border=True,
                help="desligamentos a pedido × salário médio de desligamento × N salários")
    st.caption("Estimativa de ordem de grandeza para a seleção atual, não um valor contábil.")
