"""6. Ficha do território — meso, micro ou município, escolhido aqui ou no mapa."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar

NIVEIS = [c.NIVEL_MESO, c.NIVEL_MICRO, c.NIVEL_MUNICIPIO]


def contexto_socioeconomico(dados: pd.DataFrame) -> dict[str, float]:
    """População (municípios distintos) e IDHM/PIB ponderados pela população."""
    mun = dados.drop_duplicates(c.COLUNA_MUNICIPIO)
    pop = mun[c.COLUNA_POPULACAO_2026]
    peso = pop.where(pop > 0)

    def _ponderada(coluna: str) -> float:
        validos = mun[coluna].notna() & peso.notna()
        return float((mun.loc[validos, coluna] * peso[validos]).sum() / peso[validos].sum()) if validos.any() else float("nan")

    return {"populacao": float(pop.sum()), "idhm": _ponderada(c.COLUNA_IDHM_2010),
            "pib": _ponderada(c.COLUNA_PIB_PER_CAPITA_2023), "municipios": int(len(mun))}


def semelhantes(ctx: c.Contexto, nivel: str, nome: str, n: int = 5) -> pd.DataFrame:
    """As `n` unidades do mesmo nível com população mais próxima, com KPIs."""
    coluna = c.COLUNA_POR_NIVEL_TERRITORIAL[nivel]
    base = c.filtrar(ctx.art.agregado, ctx.filtros, ignorar=("territorio",))
    m = c.agregar_metricas(base, [coluna])
    m[coluna] = m[coluna].astype(str)
    alvo = m.loc[m[coluna] == nome, c.M_POP]
    if alvo.empty or pd.isna(alvo.iloc[0]):
        return pd.DataFrame()
    m["distancia"] = (m[c.M_POP] - alvo.iloc[0]).abs()
    proximos = m.sort_values("distancia").head(n + 1)
    return pd.DataFrame({
        nivel: proximos[coluna] + proximos[coluna].map(lambda v: " (selecionado)" if v == nome else ""),
        "População 2026": [c.fmt_int(v) for v in proximos[c.M_POP]],
        "Movimentações": [c.fmt_int(v) for v in proximos[c.M_MOV]],
        "Saldo por 10 mil hab.": [c.fmt_metrica(c.M_SALDO_10K, v) for v in proximos[c.M_SALDO_10K]],
        "Saída voluntária": [c.fmt_pct(v) if ok else "amostra insuficiente" for v, ok in zip(proximos[c.M_SAIDA_VOL], proximos[c.M_AMOSTRA_OK])],
        "Salário de quem entra vs quem saiu": [c.fmt_gap(v) for v in proximos[c.M_GAP_SAL]],
    })


def render(ctx: c.Contexto) -> None:
    st.title("Ficha do território")
    c.cabecalho(ctx)
    base = c.filtrar(ctx.art.agregado, ctx.filtros, ignorar=("territorio",))
    if base.empty:
        st.info("Nenhuma movimentação com estes filtros.")
        return
    alvo_nivel, alvo_nome = st.session_state.pop("ficha_alvo", (None, None))
    if alvo_nivel in NIVEIS:
        st.session_state["ficha_nivel"] = alvo_nivel
        st.session_state["ficha_nome"] = alvo_nome
    if not st.session_state.get("ficha_nivel"):
        st.session_state["ficha_nivel"] = c.NIVEL_MESO
    col1, col2 = st.columns([1, 2])
    nivel = col1.segmented_control("Nível", NIVEIS, key="ficha_nivel") or c.NIVEL_MESO
    coluna = c.COLUNA_POR_NIVEL_TERRITORIAL[nivel]
    opcoes = sorted(base[coluna].astype(str).unique())
    if st.session_state.get("ficha_nome") not in opcoes:
        st.session_state["ficha_nome"] = opcoes[0]
    nome = col2.selectbox(nivel, opcoes, key="ficha_nome")

    dados = base[base[coluna].astype(str) == nome]
    st.subheader(nome)
    socio = contexto_socioeconomico(dados)
    nota = "" if nivel == c.NIVEL_MUNICIPIO else f" (média dos {socio['municipios']} municípios ponderada pela população)"
    st.caption(f"População 2026: {c.fmt_int(socio['populacao'])} · IDHM 2010: {c.fmt_num(socio['idhm'], 3)} · "
               f"PIB per capita 2023: {c.fmt_brl(socio['pib'])}{nota}")
    # Na ficha o delta é sempre contra o estado (mesmos filtros, sem território).
    t, ref = c.total(dados), c.total(base)
    for col, m in zip(st.columns(len(c.KPIS_PADRAO)), c.KPIS_PADRAO):
        if m in c.METRICAS_ABSOLUTAS:  # BUG-01: absoluto → participação no estado, sem seta
            col.metric(c.DEFINICOES[m].rotulo, c.fmt_metrica(m, t[m]), border=True, help=c.ajuda(m),
                       delta=c.participacao_estadual(m, t[m], ref[m]), delta_color="off", delta_arrow="off")
        else:
            col.metric(c.DEFINICOES[m].rotulo, c.fmt_metrica(m, t[m]), border=True, help=c.ajuda(m),
                       delta=c.delta_texto(m, t[m], ref[m], "vs estado"),
                       delta_color="inverse" if m in c.METRICAS_INVERSAS else "normal")
    if not t[c.M_AMOSTRA_OK]:
        st.warning(f"Amostra insuficiente: {c.fmt_int(t[c.M_MOV])} movimentações (< {c.MIN_MOVIMENTACOES}). "
                   "Leia as taxas com cautela.")

    col1, col2 = st.columns(2)
    setores = c.agregar_metricas(dados, [c.COLUNA_SETOR])
    setores = setores[setores[c.M_MOV] > 0]
    col1.plotly_chart(fig.construir_barras(setores, c.COLUNA_SETOR, c.M_MOV, "Mix setorial: onde estão as movimentações",
                                           limite=10), width="stretch")
    if not setores.empty:
        principal = setores.sort_values(c.M_MOV, ascending=False).iloc[0]
        col1.caption(f"**{principal[c.COLUNA_SETOR]}** concentra {c.fmt_pct(principal[c.M_MOV] / setores[c.M_MOV].sum())} "
                     "das movimentações.")
    mensal = c.agregar_metricas(dados, [c.COLUNA_MES])
    col2.plotly_chart(fig.construir_serie_mensal(mensal, "Mês a mês"), width="stretch")
    col2.caption(nar.legenda_serie(mensal))

    macros = c.agregar_metricas(dados, [c.COLUNA_MACROFAMILIA_CBO])
    macros = macros[macros[c.M_AMOSTRA_OK]]
    col1, col2 = st.columns(2)
    col1.markdown("**Macrofamílias que mais expandem**")
    col1.dataframe(pd.DataFrame({
        "Macrofamília (IA)": macros.sort_values(c.M_SALDO, ascending=False)[c.COLUNA_MACROFAMILIA_CBO].head(5).values,
        "Saldo": [c.fmt_int(v) for v in macros.sort_values(c.M_SALDO, ascending=False)[c.M_SALDO].head(5)],
    }), hide_index=True, width="stretch")
    col2.markdown("**Macrofamílias sob maior tensão (saída voluntária)**")
    tensas = macros.dropna(subset=[c.M_SAIDA_VOL]).sort_values(c.M_SAIDA_VOL, ascending=False).head(5)
    col2.dataframe(pd.DataFrame({
        "Macrofamília (IA)": tensas[c.COLUNA_MACROFAMILIA_CBO].values,
        "Saída voluntária": [c.fmt_pct(v) for v in tensas[c.M_SAIDA_VOL]],
        "Salário de quem entra vs quem saiu": [c.fmt_gap(v) for v in tensas[c.M_GAP_SAL]],
    }), hide_index=True, width="stretch")
    st.caption("Só macrofamílias com ≥ 100 movimentações no território.")

    st.markdown(f"**{c.plural_nivel(nivel, maiuscula=True)} com população parecida**")
    st.dataframe(semelhantes(ctx, nivel, nome), hide_index=True, width="stretch")
