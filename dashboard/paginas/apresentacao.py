"""Modo apresentação — 5 passos do pitch de 3 minutos (PLANEJAMENTO §11).

Gancho → Onde → Quem → Por quê → O que fazer. Usa sempre os filtros padrão
(indústria B–F, período inteiro), para que a história não dependa do estado
deixado na barra lateral. Cada passo: uma frase calculada e um gráfico.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar
from dashboard.paginas import causa_raiz, panorama, recomendacoes

PASSOS = ["Gancho", "Onde", "Quem", "Por quê", "O que fazer"]

CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarNav"] {display: none !important;}
.block-container {padding-top: 2rem; max-width: 1500px;}
h1 {font-size: 2.6rem !important;}
[data-testid="stMarkdownContainer"] p {font-size: 1.4rem; line-height: 1.5;}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div, [data-testid="stMetricValue"] p {font-size: 3.2rem !important; line-height: 1.2;}
[data-testid="stMetricLabel"] p {font-size: 1.25rem !important;}
</style>
"""


def _gancho(ctx: c.Contexto) -> None:
    st.markdown(nar.resposta_principal(ctx.df, ctx.filtros.escopo))
    t = c.total(ctx.df)
    cols = st.columns(3)
    cols[0].metric("Movimentações", c.fmt_int(t[c.M_MOV]), border=True, help=c.ajuda(c.M_MOV))
    cols[1].metric("Saldo de vagas", c.fmt_int(t[c.M_SALDO]), border=True,
                   help=f"{c.fmt_pct(t[c.M_SALDO_REL])} das movimentações")
    cols[2].metric("Desligamentos a pedido", c.fmt_pct(t[c.M_SAIDA_VOL]), border=True, help=c.ajuda(c.M_SAIDA_VOL))
    st.plotly_chart(fig.construir_serie_mensal(c.agregar_metricas(ctx.df, [c.COLUNA_MES]),
                                               "Todo mês a indústria contrata e desliga quase o mesmo tanto"),
                    width="stretch")


def _onde(ctx: c.Contexto) -> None:
    dados = panorama.metricas_mapa(ctx.df, c.NIVEL_MICRO)
    st.markdown(nar.legenda_mapa(dados.drop_duplicates("rotulo"), c.M_SAIDA_VOL, "rotulo", c.NIVEL_MICRO))
    st.plotly_chart(fig.construir_mapa(dados, c.geojson_cache(), c.M_SAIDA_VOL, rotulo_territorio="rotulo"),
                    width="stretch")


def _quem(ctx: c.Contexto) -> None:
    m = nar.unidades(ctx.df)
    if m.empty:
        st.markdown("Nenhuma unidade com amostra suficiente.")
        return
    cont = m["quadrante"].value_counts()
    relevantes = nar.unidades(ctx.df, relevantes=True)
    topo = (relevantes if not relevantes.empty else m).iloc[0]
    st.markdown(
        f"De {len(m)} combinações mesorregião × setor: "
        f"{nar.contagem_quadrantes(cont, tuple(c.QUADRANTES))}. A mais tensa: "
        f"**{topo[c.COLUNA_SETOR]} – {topo[c.COLUNA_REGIAO]}** ({topo['motor']})."
    )
    rotulo = m[c.COLUNA_SETOR].astype(str) + " – " + m[c.COLUNA_REGIAO].astype(str)
    st.plotly_chart(fig.construir_matriz(m, rotulo), width="stretch")


def _por_que(ctx: c.Contexto) -> None:
    perfil, _ = causa_raiz.perfil_filtrado(ctx)
    t = c.total(ctx.df)
    texto = (f"Quem entra ganha {c.fmt_pct(t[c.M_GAP_SAL], 0)} do salário de quem sai "
             f"({c.fmt_brl(t[c.M_SAL_ADM])} vs {c.fmt_brl(t[c.M_SAL_DESL])}).")
    if perfil is not None and not perfil.empty:
        por_faixa = c.medianas_perfil(perfil, [c.COLUNA_FAIXA_ESCOLARIDADE])
        por_faixa = por_faixa.set_index(c.COLUNA_FAIXA_ESCOLARIDADE).reindex(
            [f for f in causa_raiz.ORDEM_FAIXAS if f in set(por_faixa[c.COLUNA_FAIXA_ESCOLARIDADE])]).reset_index()
        st.markdown(texto + " " + causa_raiz.legenda_compressao(por_faixa, c.COLUNA_FAIXA_ESCOLARIDADE))
        st.plotly_chart(fig.construir_salario_por_categoria(por_faixa, c.COLUNA_FAIXA_ESCOLARIDADE,
                                                            "Mediana salarial por escolaridade"), width="stretch")
    else:
        st.markdown(texto)


def _o_que_fazer(ctx: c.Contexto) -> None:
    recs = c.gerar_recomendacoes(ctx.df, mediana_regional=recomendacoes.medianas_regionais(ctx),
                                  ref=c.total(ctx.ref), cbos=c.filtrar_cbo(ctx),
                                  descricoes=c.descricoes_cbo_cache())
    if not recs:
        st.markdown("Nenhuma regra disparou com amostra suficiente.")
        return
    alavancas = {r.alavanca for r in recs}
    # A mais prioritária de cada alavanca primeiro, para mostrar a variedade de ações.
    destaque = list({r.alavanca: r for r in reversed(recs)}.values())
    destaque = sorted(destaque, key=lambda r: r.prioridade, reverse=True)
    destaque += [r for r in recs if r not in destaque]
    st.markdown(f"**{len(recs)} recomendações** em {len(alavancas)} alavancas, cada uma ligada a uma "
                "macrofamília da IA. As prioritárias de cada alavanca:")
    cols = st.columns(3)
    for col, r in zip(cols, destaque[:3]):
        with col.container(border=True, height="stretch"):
            st.markdown(f"**{r.alavanca}**")
            st.markdown(f"{r.regiao} · {r.macrofamilia}")
            st.caption(r.evidencia)
    por_alavanca = (pd.DataFrame({"alavanca": [r.alavanca for r in recs], c.M_MOV: [r.movimentacoes for r in recs]})
                    .groupby("alavanca", as_index=False)[c.M_MOV].sum().assign(**{c.M_AMOSTRA_OK: True}))
    st.plotly_chart(fig.construir_barras(por_alavanca, "alavanca", c.M_MOV,
                                         "Movimentações cobertas por cada alavanca"), width="stretch")


CONTEUDO = [_gancho, _onde, _quem, _por_que, _o_que_fazer]


VAR_CHAVE = "PAINEL_CHAVE_APRESENTACAO"


def acesso_liberado(chave_configurada: str, chave_informada: str | None) -> bool:
    """Sem chave configurada, basta conhecer a URL; com chave, ela precisa bater."""
    return not chave_configurada or chave_informada == chave_configurada


def render(ctx_global: c.Contexto) -> None:
    # A página fica fora do menu; com `PAINEL_CHAVE_APRESENTACAO` definida, só
    # abre por /apresentacao?chave=<valor>. A liberação vale para a sessão,
    # porque os botões Anterior/Próximo reexecutam a página.
    chave = os.environ.get(VAR_CHAVE, "").strip()
    if not st.session_state.get("apresentacao_ok"):
        if not acesso_liberado(chave, st.query_params.get("chave")):
            st.title("Página não encontrada")
            st.caption("Use o menu lateral para navegar pelo painel.")
            return
        st.session_state["apresentacao_ok"] = True
    st.markdown(CSS, unsafe_allow_html=True)
    ctx = c.contexto_padrao(ctx_global.art)
    passo = int(st.session_state.get("passo", 0)) % len(PASSOS)

    topo = st.columns([5, 1.4, 1.4, 1.1])
    topo[0].title(f"{passo + 1}/{len(PASSOS)} · {PASSOS[passo]}")
    if topo[1].button("Anterior", icon=":material/arrow_back:", disabled=passo == 0, width="stretch"):
        st.session_state["passo"] = passo - 1
        st.rerun()
    if topo[2].button("Próximo", icon=":material/arrow_forward:", disabled=passo == len(PASSOS) - 1,
                      type="primary", width="stretch"):
        st.session_state["passo"] = passo + 1
        st.rerun()
    if topo[3].button("Sair", icon=":material/close:", width="stretch"):
        st.session_state["passo"] = 0
        st.switch_page(st.session_state["_paginas"]["panorama"])
    st.progress((passo + 1) / len(PASSOS))
    CONTEUDO[passo](ctx)
