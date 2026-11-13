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
    perfil = perfil[c.mascara_escopo(perfil, ctx.filtros.escopo)]
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
    c.ALAVANCA_FORMACAO: "O grupo cresce, mas repõe com gente menos qualificada ou o contratado não fica: "
                         "formar para as ocupações que mais giram.",
    c.ALAVANCA_MOBILIDADE: "A mesma ocupação e nível fecha vagas noutra mesorregião, por dispensa e não por "
                           "pedido de saída: há gente experiente para atrair de lá.",
    c.ALAVANCA_AUTOMACAO: "Muitos postos de nível básico, e o emprego não cresce.",
    c.ALAVANCA_RETENCAO: "Saem muitos a pedido mesmo sem salário menor: o problema não é só dinheiro.",
}


def acao_curta(r: c.Recomendacao) -> str:
    """A ação em uma linha legível: na formação, só as 3 primeiras ocupações, pelo nome curto."""
    if r.alavanca == c.ALAVANCA_FORMACAO and r.extras.get("cbos"):
        nomes = [c.nome_curto_cbo(d) for _, d, _ in r.extras["cbos"][:3]]
        lista = ", ".join(nomes[:-1]) + " e " + nomes[-1] if len(nomes) > 1 else nomes[0]
        return f"Formar {lista} em {r.regiao}"
    return r.extras.get("acao") or f"{r.alavanca}: {r.macrofamilia} em {r.regiao}"


def texto_top3(top: list[c.Recomendacao]) -> str:
    """REC-04: uma linha por ação: o quê, onde, o número que sustenta e quem age."""
    return "\n".join(
        f"{i}. **{acao_curta(r)}.** {r.extras.get('destaque', '')} · "
        f"{c.fmt_int(r.movimentacoes)} movimentações · **{r.quem_age}**, {r.horizonte}."
        for i, r in enumerate(top, 1))


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
                   *([f"   - Ação: {r.extras['acao']}."] if r.extras.get("acao") else []),
                   f"   - Quem age: {r.quem_age} · Horizonte: {r.horizonte}.",
                   f"   - KPI e meta: {r.kpi}.",
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
    recs = c.gerar_recomendacoes(ctx.df, mediana_regional=medianas_regionais(ctx), ref=c.total(ctx.ref),
                                  cbos=c.filtrar_cbo(ctx), descricoes=c.descricoes_cbo_cache())
    prioridades = classificar_prioridade(recs)
    ref = c.total(ctx.df)
    st.markdown(
        "Cada problema encontrado no diagnóstico aponta para uma **ação** que a empresa pode tomar. "
        f"Ao todo, **{len(recs)} recomendações**, agrupadas abaixo por ação."
    )
    if not recs:
        st.info("Nenhuma regra disparou com dados suficientes nesta seleção.")
    else:
        top3 = c.top_executivo(recs)
        with st.container(border=True, key="rx-top3"):
            st.markdown(f"#### As {len(top3)} ações de maior impacto")
            st.markdown(texto_top3(top3))
            st.caption("Uma por alavanca: a de maior prioridade (severidade × movimentações) dentro de cada uma; "
                       "entre as alavancas, as de mais movimentações afetadas. Muda com os filtros.")
        st.subheader("Prioridades")
        grupos = agrupar_por_alavanca(recs)
        colunas = st.columns(min(3, len(grupos)))
        for i, (alavanca, itens) in enumerate(grupos.items()):
            with colunas[i % len(colunas)].container(border=True, height="stretch"):
                st.markdown(f"**{alavanca}**")
                st.caption(POR_QUE_ALAVANCA.get(alavanca, ""))
                st.markdown("\n".join(f"- {r.extras['origem']} → {r.regiao} · {r.macrofamilia}" if r.extras.get("origem")
                                      else f"- {r.macrofamilia} · {r.regiao}" for r in itens[:3])
                            + (f"\n\n…e mais {len(itens) - 3}" if len(itens) > 3 else ""))
                if itens[0].extras.get("cbos"):  # REC-01: o que formar, na recomendação mais prioritária
                    st.caption("O que formar (" + itens[0].regiao + "): "
                               + ", ".join(f"{d} ({cod})" for cod, d, _ in itens[0].extras["cbos"]))
                st.markdown(f"**{len(itens)}** {'recomendação' if len(itens) == 1 else 'recomendações'} · "
                            f"{c.fmt_int(sum(r.movimentacoes for r in itens))} movimentações")

        tabela = pd.DataFrame([{
            "Prioridade": prioridades[i], "Alavanca": r.alavanca, "Mesorregião": r.regiao,
            "Macrofamília (IA)": r.macrofamilia, "Nível-alvo": r.nivel_alvo, "Movimentações": int(r.movimentacoes),
            "Ação": r.extras.get("acao", ""),
            "Quem age": r.quem_age, "Horizonte": r.horizonte, "KPI e meta": r.kpi,
            "O que formar (CBOs de maior volume)": "; ".join(f"{cod} {d}" for cod, d, _ in r.extras.get("cbos", [])),
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
    col1.metric("Desligamentos a pedido", c.fmt_int(t[c.COLUNA_DESLIGAMENTOS_A_PEDIDO]), border=True,
                help="Quantas pessoas pediram para sair no período (tipo de desligamento 40 do CAGED).")
    col2.metric("Salário médio de quem sai", c.fmt_brl(t[c.M_SAL_DESL]), border=True, help=c.ajuda(c.M_SAL_DESL))
    col3.metric("Custo estimado de reposição", c.fmt_brl_escala(custo), border=True,
                help="desligamentos a pedido × salário médio de desligamento × N salários")
    st.caption("Estimativa de ordem de grandeza para a seleção atual, não um valor contábil.")
