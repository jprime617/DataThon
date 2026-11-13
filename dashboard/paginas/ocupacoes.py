"""4. Ocupações (IA) — "Que profissional falta?"."""

from __future__ import annotations

import unicodedata

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar
from src.mapeamentos import FAMILIA_POR_PREFIXO_CBO, MACROFAMILIAS

REGRAS = """
**A. Ofício, não setor.** A macrofamília é o que a pessoa faz, nunca o setor do empregador: faxineira em fábrica têxtil é *Serviços de apoio*; costureira é *Têxtil* em qualquer setor.

**B. Conjunto fechado de 11 famílias + "Não classificado".** O prefixo da CBO sugere a família (ex.: 784 → Operação de linha; 72/73 → Metalmecânica); a IA só diverge com justificativa — sem ela, vale a sugestão.

**C. Nível de qualificação em 4 degraus** (Básico < Qualificado < Técnico < Superior). O 1º dígito da CBO dá o ponto de partida; a IA ajusta com justificativa (caso típico: ocupações elementares rebaixadas para Básico).

**D. Liderança é uma marca, não um nível.** Supervisores, mestres e gerentes ficam na família e no nível do ofício que lideram.
"""


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()


def buscar_cbo(mapa: pd.DataFrame, termo: str) -> pd.DataFrame:
    """Busca por código ou descrição (sem acento, sem caixa)."""
    if not termo.strip():
        return mapa
    alvo = _normalizar(termo.strip())
    return mapa[mapa["cbo2002ocupação"].astype(str).str.contains(alvo, regex=False)
                | mapa["descricao"].map(_normalizar).str.contains(alvo, regex=False)]


def render(ctx: c.Contexto) -> None:
    st.title("Que profissional falta?")
    c.cabecalho(ctx)
    st.markdown("A IA agrupou as **ocupações (CBO)** em macrofamílias por ofício e nível de qualificação. "
                "Isso revela o que a CNAE esconde: *quem* gira dentro de cada setor.")

    if not ctx.df.empty:
        por = c.agregar_metricas(ctx.df, [c.COLUNA_MACROFAMILIA_CBO, c.COLUNA_NIVEL_QUALIFICACAO])
        st.plotly_chart(fig.construir_treemap(por), width="stretch")
        macros = c.agregar_metricas(ctx.df, [c.COLUNA_MACROFAMILIA_CBO])
        piso = max(c.MIN_MOVIMENTACOES, nar.FRACAO_RELEVANCIA * float(macros[c.M_MOV].sum()))
        macros = macros[(macros[c.M_MOV] >= piso)
                        & (macros[c.COLUNA_MACROFAMILIA_CBO].astype(str) != c.NAO_CLASSIFICADO)
                        ].dropna(subset=[c.M_SAIDA_VOL])
        niveis = c.agregar_metricas(ctx.df, [c.COLUNA_NIVEL_QUALIFICACAO]).set_index(c.COLUNA_NIVEL_QUALIFICACAO)
        if not macros.empty:
            topo = macros.loc[macros[c.M_SAIDA_VOL].idxmax()]
            basico = niveis[c.M_MOV].get("Básico", 0) / max(niveis[c.M_MOV].sum(), 1)
            st.caption(f"Maior saída voluntária: **{topo[c.COLUNA_MACROFAMILIA_CBO]}** "
                       f"({c.fmt_pct(topo[c.M_SAIDA_VOL])}). Ocupações de nível Básico respondem por "
                       f"{c.fmt_pct(basico)} das movimentações deste recorte.")

    mapa, divergencias, prompt = c.cbo_cache()
    st.subheader("Explorador de ocupações")
    if mapa is None:
        st.info("Classificação da IA (cbo_macrofamilias.csv) indisponível neste ambiente.")
    else:
        termo = st.text_input("Buscar por código ou descrição", placeholder="ex.: soldador, 784205, costureira")
        achados = buscar_cbo(mapa, termo).fillna({"justificativa": ""})
        st.dataframe(
            achados.rename(columns={"cbo2002ocupação": "CBO", "descricao": "Descrição", "macrofamilia": "Macrofamília",
                                    "nivel_qualificacao": "Nível", "lideranca": "Liderança",
                                    "justificativa": "Justificativa da IA"}),
            hide_index=True, width="stretch", height=320,
        )
        st.caption(f"{c.fmt_int(len(achados))} de {c.fmt_int(len(mapa))} ocupações. Justificativa vazia = a IA "
                   "seguiu a família sugerida pelo prefixo e o nível do grande grupo.")

    # Auditoria da IA é assunto técnico: fica recolhida (M3.C8).
    with st.expander("Aprofundar: como a IA classificou as ocupações (auditoria)"):
        aba_conc, regras, aba_prompt = st.tabs(["Concordância", "Regras da taxonomia", "Prompt enviado à IA"])
        with aba_conc:
            meta = (ctx.art.metadados or {}).get("ia", {})
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Concordância na família", c.fmt_pct(meta.get("concordancia_familia")), border=True,
                        help="Comparação: " + meta.get("comparacao", "mesma IA, 2ª rodada com a ordem dos códigos embaralhada")
                        + ".")
            col2.metric("Concordância no nível", c.fmt_pct(meta.get("concordancia_nivel")), border=True)
            col3.metric("Não classificado", c.fmt_pct(meta.get("nao_classificado_ponderado"), 2), border=True,
                        help="Ponderado pelas movimentações.")
            col4.metric("Ocupações classificadas", c.fmt_int(len(mapa)) if mapa is not None else "—", border=True)
            if meta.get("modelo"):
                st.caption(f"Modelo: {meta.get('modelo')} ({meta.get('provedor', '')}), classificação de "
                           f"{str(meta.get('gerado_em', ''))[:10]}. A IA roda no pipeline, nunca no painel."
                           + (f" {meta['nota'][0].upper()}{meta['nota'][1:]}." if meta.get("nota") else "")
                           + (f" Concordância medida em: {meta['comparacao']}." if meta.get("comparacao") else ""))
            if divergencias is not None:
                st.markdown("**Maiores divergências entre as rodadas, por volume**")
                st.dataframe(divergencias.head(10).rename(columns={
                    "cbo2002ocupação": "CBO", "descricao": "Descrição", "movimentacoes": "Movimentações",
                    "macrofamilia_r1": "Família (1ª)", "macrofamilia_r2": "Família (2ª)",
                    "nivel_r1": "Nível (1ª)", "nivel_r2": "Nível (2ª)"}),
                    hide_index=True, width="stretch",
                    column_config={"Movimentações": st.column_config.NumberColumn(format="localized")})
                so_nivel = int((divergencias["macrofamilia_r1"] == divergencias["macrofamilia_r2"]).sum())
                st.caption(f"Em divergência, vale a 1ª rodada. {so_nivel} das {len(divergencias)} divergências são só de "
                           "nível, com a família igual nas duas rodadas.")
        with regras:
            st.markdown(REGRAS)
            st.caption(f"{len(MACROFAMILIAS) - 1} macrofamílias + Não classificado; "
                       f"{len(FAMILIA_POR_PREFIXO_CBO)} prefixos de desempate.")
        with aba_prompt:
            if prompt:
                st.code(prompt[:6000] + ("\n…" if len(prompt) > 6000 else ""), language=None, wrap_lines=True)
                st.download_button("Baixar o prompt completo", prompt.encode("utf-8"),
                                   file_name="prompt_classificacao_cbo.txt", icon=":material/download:")
