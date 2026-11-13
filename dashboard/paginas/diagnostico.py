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
            "Causas": ", ".join(selos) or "—",
            "Movimentações": int(u[c.M_MOV]),
            "Rotatividade descontada": c.fmt_pct(u[c.M_ROT_DESC]),
            "Saída voluntária": c.fmt_pct(u[c.M_SAIDA_VOL]),
            "Desligamento precoce": c.fmt_pct(u[c.M_PRECOCE]),
            "Salário de quem entra vs quem saiu": c.fmt_gap(u[c.M_GAP_SAL]),
            "Saldo": c.fmt_int(u[c.M_SALDO]),
        })
    return pd.DataFrame(linhas)


CARTOES_MAX = 6
# Rótulo curto de cada sintoma de tensão no cartão de alerta.
ROTULO_SINTOMA = {c.M_ROT_DESC: "Rotatividade", c.M_SAIDA_VOL: "Saem a pedido",
                  c.M_PRECOCE: "Saem com < 1 ano"}


def sintoma_principal(u: pd.Series) -> str:
    """O sintoma com o maior z-score na unidade (o que mais puxa a tensão)."""
    presentes = [n for n in c.PESOS_TENSAO_PADRAO if pd.notna(u.get(f"z_{n}"))]
    return max(presentes, key=lambda n: u[f"z_{n}"]) if presentes else c.M_SAIDA_VOL
_CLASSE_QUADRANTE = {c.Q_APAGAO: "apagao", c.Q_PRESSAO: "pressao"}


def frase_porque(u: pd.Series, selos: list[str], saida_ref: float) -> str:
    """O "por quê" de uma unidade em alerta, numa frase sem jargão.

    Sem causa isolada devolve "": o cartão já mostra o sintoma que mais pesa,
    e a frase repetida em todos os cartões só poluía (M3.C8).
    """
    saida, gap = u[c.M_SAIDA_VOL], u[c.M_GAP_SAL]
    if c.CAUSA_SALARIAL in selos:
        return (f"Quem entra ganha {c.fmt_pct(gap, 0)} do salário de quem sai, "
                f"e {c.fmt_pct(saida, 0)} dos desligamentos são a pedido.")
    if c.CAUSA_RETENCAO in selos:
        return (f"{c.fmt_pct(saida, 0)} dos desligamentos são a pedido (estado: {c.fmt_pct(saida_ref, 0)}), "
                "e o salário de entrada não é menor: o problema é reter.")
    if c.CAUSA_QUALIFICACAO in selos:
        return "Contrata gente menos escolarizada do que a que sai, numa área que pede técnico ou superior."
    return ""


def _cartao(u: pd.Series, segunda: str, selos: list[str], ref: pd.Series, i: int) -> None:
    quadrante = u["quadrante"]
    with st.container(border=True, key=f"rx-alerta-{_CLASSE_QUADRANTE[quadrante]}-{i}"):
        st.markdown(f"**{u[segunda]}**  \n{u[c.COLUNA_REGIAO]}")
        st.html(f'<span class="rx-semaforo rx-{_CLASSE_QUADRANTE[quadrante]}">{quadrante}</span>')
        frase = frase_porque(u, selos, ref[c.M_SAIDA_VOL])
        if frase:
            st.markdown(frase)
        a, b = st.columns(2)
        nome = sintoma_principal(u)
        a.metric(ROTULO_SINTOMA[nome], c.fmt_pct(u[nome], 0),
                 delta=c.delta_texto(nome, u[nome], ref[nome], "vs SC"),
                 delta_color="inverse", help=c.DEFINICOES[nome].formula)
        b.metric("Saldo de vagas", c.fmt_int(u[c.M_SALDO]), help=f"{c.fmt_int(u[c.M_MOV])} movimentações")


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
        f"{contagem.get(c.Q_APAGAO, 0)} grupos em **{c.Q_APAGAO}** e {contagem.get(c.Q_PRESSAO, 0)} em "
        f"**{c.Q_PRESSAO}**, de {len(m)} analisados"
        + (f" ({excluidas} ficaram fora por ter poucos dados)" if excluidas else "")
        + ". As linhas pontilhadas marcam a média; quanto maior a bolha, mais movimentações."
    )

    st.subheader("Alertas, do mais tenso ao menos tenso")
    ref = c.total(ctx.df)
    saida_ref = ref[c.M_SAIDA_VOL]
    frac_tecnica = c.fracao_por_nivel(ctx.df, por, c.NIVEIS_QUALIFICADOS)
    tabela = tabela_alertas(m, segunda, saida_ref, frac_tecnica)
    if tabela.empty:
        st.caption("Nenhuma unidade nos quadrantes de alerta.")
    else:
        alerta = m[m["quadrante"].isin([c.Q_APAGAO, c.Q_PRESSAO])]
        piso = max(c.MIN_MOVIMENTACOES, nar.FRACAO_RELEVANCIA * float(m[c.M_MOV].sum()))
        alerta = alerta.assign(_rel=alerta[c.M_MOV] >= piso).sort_values(["_rel", "tensao"], ascending=False)
        colunas = st.columns(3)
        for i, (_, u) in enumerate(alerta.head(CARTOES_MAX).iterrows()):
            selos = c.causas(u, saida_ref=saida_ref,
                             fracao_tecnica=float(frac_tecnica.get((u[c.COLUNA_REGIAO], u[segunda]), 0.0)))
            with colunas[i % 3]:
                _cartao(u, segunda, selos, ref, i)
        st.caption(f"Laranja-escuro = {c.Q_APAGAO}: perde gente e cresce pouco. Amarelo = {c.Q_PRESSAO}: "
                   "cresce, mas perde gente. Cartão sem frase = salário, qualificação e retenção não explicam "
                   "sozinhos a tensão; o número mostra o sintoma que mais pesa.")
        with st.expander(f"Ver as {len(tabela)} unidades em alerta numa tabela"):
            st.dataframe(tabela, hide_index=True, width="stretch",
                         column_config={"Movimentações": st.column_config.NumberColumn(format="localized")})
            st.caption("Causas: Salarial = quem entra ganha mais de 5% menos que quem saiu; Qualificação = entra gente "
                       "menos escolarizada numa área técnica; Retenção = saída a pedido 5 p.p. acima do estado sem que o "
                       "salário de entrada seja menor.")

    c.baixar_csv(m.drop(columns=[col for col in m.columns if col.startswith(("soma_", "n_"))]),
                 "diagnostico_matriz.csv")
