"""1. Panorama — "Onde está o problema?"."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar

METRICAS_MAPA = [c.M_SALDO_10K, c.M_ROT_DESC, c.M_SAIDA_VOL, c.M_GAP_SAL]


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


def volume_por_municipio(df: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """Movimentações de cada município (segunda camada do mapa), com o rótulo da unidade pintada."""
    coluna = c.COLUNA_POR_NIVEL_TERRITORIAL[nivel]
    por = c.agregar_metricas(df, list(dict.fromkeys([c.COLUNA_MUNICIPIO, c.COLUNA_NOME_MUNICIPIO, coluna])))
    return pd.DataFrame({
        c.COLUNA_MUNICIPIO: por[c.COLUNA_MUNICIPIO].astype(str),
        c.COLUNA_NOME_MUNICIPIO: por[c.COLUNA_NOME_MUNICIPIO].astype(str),
        "rotulo": por[coluna].astype(str),
        c.M_MOV: por[c.M_MOV],
    })


def _mapa(ctx: c.Contexto) -> None:
    """Um único mapa de SC: o filtro troca o indicador (e a paleta); o círculo mostra o volume."""
    with st.container(border=True, key="rx-destaque"):
        escolha, nivel_col, bolha_col = st.columns([4, 4, 2], vertical_alignment="bottom")
        metrica = escolha.selectbox("O que mostrar no mapa", METRICAS_MAPA,
                                    format_func=lambda m: c.DEFINICOES[m].rotulo, key="mapa_metrica")
        nivel = nivel_col.segmented_control("Pintar por", [c.NIVEL_MESO, c.NIVEL_MICRO, c.NIVEL_MUNICIPIO],
                                            default=c.NIVEL_MESO, key="mapa_nivel") or c.NIVEL_MESO
        bolhas = bolha_col.toggle("Volume", value=False, key="mapa_bolhas",
                                  help="Círculo em cada município, do tamanho das suas movimentações.")
        dados_mapa = metricas_mapa(ctx.df, nivel)
        destaque = ctx.filtros.territorios if ctx.filtros.nivel_territorial == nivel else ()
        mapa, lado = st.columns([3, 1], gap="medium")
        with mapa:
            evento = st.plotly_chart(
                fig.construir_mapa(dados_mapa, c.geojson_cache(), metrica, rotulo_territorio="rotulo",
                                   destaque=destaque, altura=640,
                                   bolhas=volume_por_municipio(ctx.df, nivel) if bolhas else None),
                width="stretch", on_select="rerun", selection_mode="points", key="mapa")
        with lado:
            c.cartao_destaque(ctx, metrica)
            st.caption(nar.legenda_mapa(dados_mapa.drop_duplicates("rotulo"), metrica, "rotulo", nivel)
                       + " Clique num território para abrir a ficha.")
    pontos = getattr(getattr(evento, "selection", None), "points", None) or []
    if pontos:
        alvo = pontos[0].get("customdata")
        alvo = alvo[0] if isinstance(alvo, list) else alvo
        if alvo:
            st.session_state["ficha_alvo"] = (nivel, str(alvo))
            st.switch_page(st.session_state["_paginas"]["ficha"])


def _achados(ctx: c.Contexto) -> None:
    # Achados do estado (só escopo e período): aplicar um deles não pode
    # reescrever a própria lista, senão os demais somem.
    achados = nar.principais_achados(ctx.ref)
    if not achados:
        st.caption("Sem dados suficientes para gerar achados nesta seleção.")
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


def _secoes_e_meses(ctx: c.Contexto) -> None:
    st.dataframe(ranking_secoes(ctx.df), hide_index=True, width="stretch", column_config={
        "Saldo de vagas": st.column_config.NumberColumn(format="localized"),
        "Movimentações": st.column_config.NumberColumn(format="localized"),
        "Rotatividade descontada": st.column_config.ProgressColumn(
            "Troca de equipe no ano", format="percent", min_value=0.0, max_value=1.0,
            help="Rotatividade descontada (MTE): min(admissões, desligamentos descontados) ÷ estoque de "
                 "31/12/2025 (RAIS). Oficial: SC 33,6%, Brasil 34,2%."),
        "Saída voluntária": st.column_config.ProgressColumn(
            "Saem a pedido", format="percent", min_value=0.0, max_value=1.0,
            help="Desligamentos a pedido ÷ desligamentos. Vazio = menos de 100 movimentações."),
    })
    st.caption("Da seção que mais criou vagas para a que mais perdeu. Vazio = poucos dados.")
    mensal = c.agregar_metricas(ctx.df, [c.COLUNA_MES])
    st.plotly_chart(fig.construir_serie_mensal(mensal), width="stretch")
    st.caption(nar.legenda_serie(mensal))


def _resposta_central(ctx: c.Contexto) -> None:
    """NAR-02: a pergunta do desafio respondida em três linhas calculadas, sem rolar a página."""
    manchete = nar.resposta_principal(ctx.df, ctx.filtros.escopo).partition("\n\n")[0]
    cbos, gap_ref_cbo = c.referencia_cbo(ctx)
    resposta = nar.resposta_central(ctx.df, c.total(ctx.ref), cbos=cbos, gap_ref_cbo=gap_ref_cbo)
    t = c.total(ctx.df)
    with st.container(border=True, key="rx-resposta"):
        st.caption("RESPOSTA À PERGUNTA CENTRAL · onde há apagão ou expansão, e se renda e escolaridade explicam")
        st.markdown(f"#### {manchete}")
        if resposta is not None:
            st.markdown(f"- **Onde.** {resposta.onde}\n- {resposta.renda}\n- {resposta.escolaridade}")
        st.caption(f"{c.fmt_int(t[c.M_MOV])} movimentações · saldo {c.fmt_int(t[c.M_SALDO])} vagas · "
                   f"{c.fmt_pct(t[c.M_SAIDA_VOL])} dos desligamentos a pedido · grupos = mesorregião × setor com "
                   f"≥ {c.MIN_MOVIMENTACOES} movimentações. Critérios de \"explica\" na Metodologia.")


def render(ctx: c.Contexto) -> None:
    st.title("Onde está o problema?", anchor=False)
    c.cabecalho(ctx)
    if ctx.df.empty:
        st.info("Nenhuma movimentação com estes filtros. Use **Limpar filtros** na barra lateral.")
        return

    _resposta_central(ctx)

    _mapa(ctx)
    c.cartoes_kpi(ctx, c.METRICAS_TEMAS)

    with st.expander("Aprofundar: principais achados", icon=":material/lightbulb:"):
        _achados(ctx)
    with st.expander("Aprofundar: seções e evolução mês a mês", icon=":material/bar_chart:"):
        _secoes_e_meses(ctx)

    reagregado = c.agregar_metricas(ctx.df, [c.COLUNA_REGIAO, c.COLUNA_SETOR, c.COLUNA_MACROFAMILIA_CBO,
                                             c.COLUNA_NIVEL_QUALIFICACAO])
    c.baixar_csv(reagregado[reagregado[c.M_MOV] > 0], "panorama_recorte.csv")
