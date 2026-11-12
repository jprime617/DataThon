"""2. Diagnóstico — "Quem precisa de atenção urgente?"."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar

UNIDADES = {"Mesorregião × setor": c.COLUNA_SETOR, "Mesorregião × macrofamília (IA)": c.COLUNA_MACROFAMILIA_CBO}


def rotulo_unidade(m: pd.DataFrame, segunda: str) -> pd.Series:
    return m[segunda].astype(str) + " – " + m[c.COLUNA_REGIAO].astype(str)


def tabela_alertas(m: pd.DataFrame, segunda: str, saida_ref: float, frac_tecnica: pd.Series) -> pd.DataFrame:
    """Unidades em Apagão ou Expansão sob pressão, com motor e selos de causa."""
    alerta = m[m["quadrante"].isin([c.Q_APAGAO, c.Q_PRESSAO])].copy()
    # Unidades relevantes (≥ 1% das movimentações) primeiro; dentro de cada
    # grupo, da mais tensa para a menos tensa.
    piso = max(c.MIN_MOVIMENTACOES, nar.FRACAO_RELEVANCIA * float(m[c.M_MOV].sum()))
    alerta["_relevante"] = alerta[c.M_MOV] >= piso
    alerta = alerta.sort_values(["_relevante", "tensao"], ascending=False)
    linhas = []
    for _, u in alerta.iterrows():
        chave = (u[c.COLUNA_REGIAO], u[segunda])
        selos = c.causas(u, saida_ref=saida_ref, fracao_tecnica=float(frac_tecnica.get(chave, 0.0)))
        linhas.append({
            "Unidade": f"{u[segunda]} – {u[c.COLUNA_REGIAO]}",
            "Quadrante": u["quadrante"],
            "Principal motor": u["motor"],
            "Causas": ", ".join(selos) or "—",
            "Tensão (z)": c.fmt_num(u["tensao"], 2).replace("-", "−"),
            "Movimentações": int(u[c.M_MOV]),
            "Saída voluntária": c.fmt_pct(u[c.M_SAIDA_VOL]),
            "Gap salarial": c.fmt_razao(u[c.M_GAP_SAL]),
            "Saldo": c.fmt_int(u[c.M_SALDO]),
        })
    return pd.DataFrame(linhas)


def render(ctx: c.Contexto) -> None:
    st.title("Quem precisa de atenção urgente?")
    c.cabecalho(ctx)
    escolha = st.segmented_control("Unidade de análise", list(UNIDADES), default=list(UNIDADES)[0],
                                   key="diag_unidade") or list(UNIDADES)[0]
    segunda = UNIDADES[escolha]
    por = [c.COLUNA_REGIAO, segunda]
    m = c.matriz_diagnostico(ctx.df, por)
    if m.empty:
        st.info("Nenhuma unidade com ≥ 100 movimentações nesta seleção.")
        return

    st.plotly_chart(fig.construir_matriz(m, rotulo_unidade(m, segunda)), width="stretch")
    contagem = m["quadrante"].value_counts()
    excluidas = len(c.agregar_metricas(ctx.df, por).query(f"{c.M_MOV} > 0")) - len(m)
    st.caption(
        f"{contagem.get(c.Q_APAGAO, 0)} unidades em **{c.Q_APAGAO}** e {contagem.get(c.Q_PRESSAO, 0)} em "
        f"**{c.Q_PRESSAO}**, de {len(m)} com amostra suficiente ({excluidas} com < 100 movimentações ficaram "
        "fora). Eixos em z-score entre as unidades: 0 = média do recorte."
    )

    st.subheader("Alertas, do mais tenso ao menos tenso")
    ref = c.total(ctx.df)
    tabela = tabela_alertas(m, segunda, ref[c.M_SAIDA_VOL],
                            c.fracao_por_nivel(ctx.df, por, c.NIVEIS_QUALIFICADOS))
    if tabela.empty:
        st.caption("Nenhuma unidade nos quadrantes de alerta.")
    else:
        st.dataframe(tabela, hide_index=True, width="stretch",
                     column_config={"Movimentações": st.column_config.NumberColumn(format="localized")})
        st.caption("Primeiro as unidades com ≥ 1% das movimentações do recorte, da mais à menos tensa. Causas: Salarial = gap < 0,95; Qualificação = gap de escolaridade ≤ −0,10 com Técnico + "
                   "Superior ≥ 50%; Retenção = saída voluntária ≥ estado + 5 p.p. com gap ≥ 1.")

    # Com um só componente de tensão não há peso para variar; volta no M4.C6.
    if len(c.PESOS_TENSAO_PADRAO) > 1:
        with st.expander("Sensibilidade: o top 10 muda com outros pesos?"):
            st.caption("Pesos iniciais iguais (PLANEJAMENTO §7.1). Mude-os e veja quantas unidades permanecem "
                       "no top 10 de tensão.")
            cols = st.columns(len(c.PESOS_TENSAO_PADRAO))
            pesos = {nome: col.slider(f"Peso: {c.ROTULO_COMPONENTE[nome]}", 0.0, 3.0, 1.0, 0.5)
                     for col, nome in zip(cols, c.PESOS_TENSAO_PADRAO)}
            if sum(pesos.values()) == 0:
                st.warning("Ao menos um peso precisa ser maior que zero.")
            else:
                alt = c.matriz_diagnostico(ctx.df, por, pesos_tensao=pesos)
                base10 = list(rotulo_unidade(m, segunda).head(10))
                alt10 = list(rotulo_unidade(alt, segunda).head(10))
                mantidas = len(set(base10) & set(alt10))
                st.markdown(f"**{mantidas} de {min(10, len(base10))}** unidades permanecem no top 10.")
                st.dataframe(pd.DataFrame({"Pesos iguais": pd.Series(base10), "Pesos escolhidos": pd.Series(alt10)},
                                          index=range(1, max(len(base10), len(alt10)) + 1)), width="stretch")

    c.baixar_csv(m.drop(columns=[col for col in m.columns if col.startswith(("soma_", "n_"))]),
                 "diagnostico_matriz.csv")
