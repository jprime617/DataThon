"""1. Panorama — "Onde está o problema?"."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar

METRICAS_MAPA = [c.M_SAIDA_VOL, c.M_GAP_SAL, c.M_SALDO_10K, c.M_GAP_ESC]


def metricas_mapa(df: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """Métricas da unidade territorial, replicadas em cada município dela."""
    coluna = c.COLUNA_POR_NIVEL_TERRITORIAL[nivel]
    municipios = df[[c.COLUNA_MUNICIPIO, c.COLUNA_NOME_MUNICIPIO, c.COLUNA_REGIAO,
                     c.COLUNA_MICRORREGIAO]].drop_duplicates(c.COLUNA_MUNICIPIO).astype(str)
    por = c.agregar_metricas(df, [coluna])
    por[coluna] = por[coluna].astype(str)
    mapa = municipios.merge(por, on=coluna, how="left")
    mapa["rotulo"] = mapa[coluna]
    return mapa


def ranking_secoes(df: pd.DataFrame) -> pd.DataFrame:
    """R7.3: seções por saldo (decrescente), com a rotatividade descontada ao lado."""
    por = c.agregar_metricas(df, [c.COLUNA_SECAO_INDUSTRIAL])
    por = por[por[c.M_MOV] > 0].sort_values(c.M_SALDO, ascending=False, kind="stable")
    return pd.DataFrame({
        "Seção (CNAE)": por[c.COLUNA_SECAO_INDUSTRIAL].astype(str).values,
        "Saldo de vagas": por[c.M_SALDO].astype("int64").values,
        "Rotatividade descontada": por[c.M_ROT_DESC].where(por[c.M_AMOSTRA_OK]).values,
        "Saída voluntária": por[c.M_SAIDA_VOL].where(por[c.M_AMOSTRA_OK]).values,
        "Movimentações": por[c.M_MOV].astype("int64").values,
    })


def aplicar_achado(filtros: dict) -> None:
    """Aplica os filtros que provam um achado (callback de botão)."""
    for chave in _CHAVES_ACHADO:
        st.session_state[chave] = []
    st.session_state.update(filtros)


_CHAVES_ACHADO = ("f_terr", "f_setor", "f_macro", "f_niv")


def achado_ativo(filtros: dict, estado) -> bool:
    """O recorte atual é exatamente o que o achado aplica?"""
    if "f_nivel" in filtros and estado.get("f_nivel") != filtros["f_nivel"]:
        return False
    return all(list(estado.get(k) or []) == list(filtros.get(k, [])) for k in _CHAVES_ACHADO)


def render(ctx: c.Contexto) -> None:
    st.title("Onde está o problema?")
    c.cabecalho(ctx)
    if ctx.df.empty:
        st.info("Nenhuma movimentação com estes filtros. Use **Limpar filtros** na barra lateral.")
        return

    manchete, _, topicos = nar.resposta_principal(ctx.df, ctx.filtros.escopo).partition("\n\n")
    with st.container(border=True):
        st.markdown(f"#### {manchete}")
        if topicos:
            st.markdown(topicos)
    indicadores, painel = st.columns([5, 7], gap="large")
    with indicadores:
        c.cartoes_kpi(ctx, c.METRICAS_TEMAS)

    with painel, st.container(border=True, key="rx-destaque"):
        metrica = st.selectbox("Indicador em destaque", METRICAS_MAPA,
                               format_func=lambda m: c.DEFINICOES[m].rotulo, key="mapa_metrica")
        nivel = st.segmented_control("Pintar o mapa por", [c.NIVEL_MESO, c.NIVEL_MICRO, c.NIVEL_MUNICIPIO],
                                     default=c.NIVEL_MICRO, key="mapa_nivel") or c.NIVEL_MICRO
        c.cartao_destaque(ctx, metrica)
        dados_mapa = metricas_mapa(ctx.df, nivel)
        destaque = ctx.filtros.territorios if ctx.filtros.nivel_territorial == nivel else ()
        evento = st.plotly_chart(fig.construir_mapa(dados_mapa, c.geojson_cache(), metrica, rotulo_territorio="rotulo",
                                                    destaque=destaque),
                                 width="stretch", on_select="rerun", selection_mode="points", key="mapa")
        st.caption(nar.legenda_mapa(dados_mapa.drop_duplicates("rotulo"), metrica, "rotulo")
                   + " Clique num território para abrir a ficha.")
    pontos = getattr(getattr(evento, "selection", None), "points", None) or []
    if pontos:
        alvo = pontos[0].get("customdata")
        alvo = alvo[0] if isinstance(alvo, list) else alvo
        if alvo:
            st.session_state["ficha_alvo"] = (nivel, str(alvo))
            st.switch_page(st.session_state["_paginas"]["ficha"])

    st.divider()
    st.subheader("Principais achados")
    # Achados do estado (só escopo e período): aplicar um deles não pode
    # reescrever a própria lista, senão os demais somem.
    achados = nar.principais_achados(ctx.ref)
    if not achados:
        st.caption("Sem unidades com amostra suficiente para gerar achados nesta seleção.")
    for i, achado in enumerate(achados):
        ativo = achado_ativo(achado.filtros, st.session_state)
        with st.container(border=True, key=f"rx-achado-{i}" + ("-ativo" if ativo else "")):
            texto, botao = st.columns([5, 1])
            texto.markdown(f"**{i + 1}. {achado.titulo}** — {achado.texto}")
            if ativo:
                botao.button("Voltar ao estado", key=f"achado_{i}", on_click=aplicar_achado, args=({},),
                             icon=":material/undo:", width="stretch", type="primary")
            else:
                botao.button("Ver evidência", key=f"achado_{i}", on_click=aplicar_achado, args=(achado.filtros,),
                             icon=":material/filter_alt:", width="stretch")

    st.subheader("Seções: onde se cria e onde se perde vaga")
    st.dataframe(ranking_secoes(ctx.df), hide_index=True, width="stretch", column_config={
        "Saldo de vagas": st.column_config.NumberColumn(format="localized"),
        "Movimentações": st.column_config.NumberColumn(format="localized"),
        "Rotatividade descontada": st.column_config.ProgressColumn(
            format="percent", min_value=0.0, max_value=1.0,
            help="min(admissões, desligamentos descontados) ÷ estoque de 31/12/2025 (RAIS). "
                 "Oficial (MTE): SC 33,6%, Brasil 34,2%."),
        "Saída voluntária": st.column_config.ProgressColumn(
            format="percent", min_value=0.0, max_value=1.0,
            help="Desligamentos a pedido ÷ desligamentos. Vazio = menos de 100 movimentações."),
    })
    st.caption("Da seção que mais criou vagas para a que mais perdeu. Rotatividade descontada na definição do "
               "MTE, com o estoque da RAIS 2025; vazio = menos de 100 movimentações.")

    mensal = c.agregar_metricas(ctx.df, [c.COLUNA_MES])
    st.plotly_chart(fig.construir_serie_mensal(mensal), width="stretch")
    st.caption(nar.legenda_serie(mensal))

    reagregado = c.agregar_metricas(ctx.df, [c.COLUNA_REGIAO, c.COLUNA_SETOR, c.COLUNA_MACROFAMILIA_CBO,
                                             c.COLUNA_NIVEL_QUALIFICACAO])
    c.baixar_csv(reagregado[reagregado[c.M_MOV] > 0], "panorama_recorte.csv")
