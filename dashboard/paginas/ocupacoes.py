"""4. Ocupações (IA) — "Que profissional falta?"."""

from __future__ import annotations

import unicodedata

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar
from src.cbo_ia import ORIGEM_OVERRIDE
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


def tabela_overrides(final: pd.DataFrame | None) -> pd.DataFrame:
    """TAX-03: as CBOs com override manual, o que a IA tinha dito e o que ficou, com justificativa e autor."""
    if final is None or final.empty:
        return pd.DataFrame()
    o = final[final["origem"] == ORIGEM_OVERRIDE]
    return pd.DataFrame({
        "CBO": o["cbo"].values, "Descrição": o["descricao"].values,
        "Família da IA": o["macrofamilia_ia"].values, "Nível da IA": o["nivel_ia"].values,
        "Família final": o["macrofamilia"].values, "Nível final": o["nivel_qualificacao"].values,
        "Justificativa": o["justificativa_override"].values, "Autor": o["autor_override"].values,
    })


def _revisao_manual(final: pd.DataFrame | None) -> None:
    """TAX-03: overrides de `ia_cbo/overrides.csv`, aplicados depois da IA e do desempate."""
    tabela = tabela_overrides(final)
    if tabela.empty:
        st.caption("Nenhum override manual aplicado nesta versão dos dados.")
        return
    mudou = int(((tabela["Família da IA"] != tabela["Família final"])
                 | (tabela["Nível da IA"] != tabela["Nível final"])).sum())
    st.markdown(f"**{len(tabela)} CBOs** revisadas à mão em `ia_cbo/overrides.csv`, aplicado depois da saída da IA e "
                f"do desempate. Em **{mudou}** o override mudou a família ou o nível; nas demais, confirmou a 1ª "
                "rodada onde o prefixo da CBO não resolvia a divergência entre as rodadas.")
    st.dataframe(tabela, hide_index=True, width="stretch")


def _alem_do_prefixo(ctx: c.Contexto, mapa: pd.DataFrame | None) -> None:
    """TAX-05: por que usar IA se a CBO já tem hierarquia? As decisões da IA além do prefixo, contadas."""
    dec = c.decisoes_ia(mapa, c.filtrar_cbo(ctx))
    st.markdown(nar.texto_decisoes_ia(dec))
    if dec.empty:
        return
    contrariou = dec[dec["decisao"] == c.DECISAO_CONTRARIOU].head(5)
    st.markdown("**As 5 de maior volume em que a IA contrariou o prefixo**")
    st.dataframe(pd.DataFrame({
        "CBO": contrariou["cbo"], "Descrição": contrariou["descricao"],
        "Família pelo prefixo": contrariou["familia_prefixo"], "Família da IA": contrariou["macrofamilia"],
        "Movimentações": contrariou["movimentacoes"].astype("int64"),
        "Justificativa da IA": contrariou["justificativa"],
    }), hide_index=True, width="stretch",
        column_config={"Movimentações": st.column_config.NumberColumn(format="localized")})
    st.caption("Prefixo = a família que a tabela de desempate da regra B sugere pelos primeiros dígitos da CBO. "
               "Movimentações no recorte atual (escopo, período e filtros de setor, macrofamília e nível).")


def explorador(mapa: pd.DataFrame, final: pd.DataFrame | None) -> pd.DataFrame:
    """A classificação que o painel usa (com desempate e overrides) e a origem de cada decisão."""
    if final is None or final.empty:
        return mapa
    f = final.set_index("cbo")
    codigos = mapa["cbo2002ocupação"].astype(str).str.strip().str.zfill(6)
    resultado = mapa.copy()
    resultado["macrofamilia"] = codigos.map(f["macrofamilia"]).fillna(mapa["macrofamilia"]).values
    resultado["nivel_qualificacao"] = codigos.map(f["nivel_qualificacao"]).fillna(mapa["nivel_qualificacao"]).values
    resultado["origem"] = codigos.map(f["origem"]).fillna("").values
    return resultado


def render(ctx: c.Contexto) -> None:
    st.title("Que profissional falta?", anchor=False)
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
    st.subheader("Explorador de ocupações", anchor=False)
    if mapa is None:
        st.info("Classificação da IA (cbo_macrofamilias.csv) indisponível neste ambiente.")
    else:
        termo = st.text_input("Buscar por código ou descrição", placeholder="ex.: soldador, 784205, costureira")
        achados = buscar_cbo(explorador(mapa, c.cbo_final_cache()), termo).fillna({"justificativa": ""})
        st.dataframe(
            achados.rename(columns={"cbo2002ocupação": "CBO", "descricao": "Descrição", "macrofamilia": "Macrofamília",
                                    "nivel_qualificacao": "Nível", "lideranca": "Liderança",
                                    "justificativa": "Justificativa da IA", "origem": "Decisão"}),
            hide_index=True, width="stretch", height=320,
        )
        st.caption(f"{c.fmt_int(len(achados))} de {c.fmt_int(len(mapa))} ocupações. Justificativa vazia = a IA "
                   "seguiu a família sugerida pelo prefixo e o nível do grande grupo. Macrofamília e nível são os "
                   "finais, depois do desempate e da revisão manual; a coluna Decisão diz de onde veio cada um.")

    # Auditoria da IA é assunto técnico: fica recolhida (M3.C8).
    with st.expander("Aprofundar: como a IA classificou as ocupações (auditoria)"):
        final = c.cbo_final_cache()
        n_over = int((final["origem"] == ORIGEM_OVERRIDE).sum()) if final is not None else 0
        aba_conc, aba_alem, aba_rev, regras, aba_prompt = st.tabs(
            ["Concordância", "O que a IA acrescentou", f"Revisão manual ({n_over})", "Regras da taxonomia",
             "Prompt enviado à IA"])
        with aba_alem:
            _alem_do_prefixo(ctx, mapa)
        with aba_rev:
            _revisao_manual(final)
        with aba_conc:
            meta = (ctx.art.metadados or {}).get("ia", {})
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Concordância na família", c.fmt_pct(meta.get("concordancia_familia")), border=True,
                        help="Em quantas ocupações a classificação que vale e a classificação de auditoria deram a "
                             "mesma macrofamília.")
            col2.metric("Concordância no nível", c.fmt_pct(meta.get("concordancia_nivel")), border=True,
                        help="Em quantas ocupações as duas classificações deram o mesmo nível de qualificação.")
            col3.metric("Não classificado", c.fmt_pct(meta.get("nao_classificado_ponderado"), 2), border=True,
                        help="Ponderado pelas movimentações.")
            col4.metric("Ocupações classificadas", c.fmt_int(len(mapa)) if mapa is not None else "—", border=True,
                        help="Códigos CBO distintos que aparecem nas movimentações e receberam macrofamília e nível.")
            st.markdown(nar.auditoria_ia(meta, c.carregar_meta_rodada2(), divergencias, c.cbo_final_cache()))
            if divergencias is not None:
                st.markdown("**Maiores divergências entre as rodadas, por volume**")
                st.dataframe(divergencias.head(10).rename(columns={
                    "cbo2002ocupação": "CBO", "descricao": "Descrição", "movimentacoes": "Movimentações",
                    "macrofamilia_r1": "Família (1ª, vale)", "macrofamilia_r2": "Família (2ª, auditoria)",
                    "nivel_r1": "Nível (1ª)", "nivel_r2": "Nível (2ª)"}),
                    hide_index=True, width="stretch",
                    column_config={"Movimentações": st.column_config.NumberColumn(format="localized")})
        with regras:
            st.markdown(REGRAS)
            st.caption(f"{len(MACROFAMILIAS) - 1} macrofamílias + Não classificado; "
                       f"{len(FAMILIA_POR_PREFIXO_CBO)} prefixos de desempate.")
        with aba_prompt:
            if prompt:
                st.code(prompt[:6000] + ("\n…" if len(prompt) > 6000 else ""), language=None, wrap_lines=True)
                st.download_button("Baixar o prompt completo", prompt.encode("utf-8"),
                                   file_name="prompt_classificacao_cbo.txt", icon=":material/download:")
