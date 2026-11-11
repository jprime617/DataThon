"""Frases do painel calculadas a partir dos dados (nenhum número escrito à mão).

Funções puras: recebem recortes do agregado e devolvem texto pt-BR. São a
"voz" do painel — a resposta em uma frase da abertura, os principais achados
(cada um com os filtros que o provam) e as legendas de uma linha dos gráficos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from dashboard import comum as c


@dataclass
class Achado:
    """Uma frase de achado e os filtros (chaves de `st.session_state`) que a provam."""

    titulo: str
    texto: str
    filtros: dict = field(default_factory=dict)
    forca: float = 0.0


def periodo(df: pd.DataFrame) -> str:
    meses = sorted(df[c.COLUNA_MES].astype(str).unique())
    return f"{c.rotulo_mes(meses[0])}–{c.rotulo_mes(meses[-1])}" if meses else "—"


FRACAO_RELEVANCIA = 0.01


def unidades(df: pd.DataFrame, *, relevantes: bool = False) -> pd.DataFrame:
    """Matriz mesorregião × setor com amostra suficiente (base dos achados).

    Com ``relevantes=True``, as frases só citam unidades com ao menos 1% das
    movimentações do recorte (e no mínimo 100): uma taxa extrema sobre 126
    movimentações é ruído demais para virar a manchete de um painel estadual.
    Os z-scores continuam calculados entre todas as unidades com amostra.
    """
    m = c.matriz_diagnostico(df, [c.COLUNA_REGIAO, c.COLUNA_SETOR])
    if relevantes and not m.empty:
        piso = max(c.MIN_MOVIMENTACOES, FRACAO_RELEVANCIA * float(m[c.M_MOV].sum()))
        m = m[m[c.M_MOV] >= piso]
    return m


def resposta_principal(df: pd.DataFrame, escopo: str = c.ESCOPO_INDUSTRIA) -> str:
    """A pergunta de negócio respondida em uma frase, com os números do recorte."""
    if df is None or df.empty:
        return "Nenhuma movimentação na seleção atual — ajuste ou limpe os filtros."
    t = c.total(df)
    nome = "Na indústria catarinense" if escopo == c.ESCOPO_INDUSTRIA else "Na economia catarinense"
    frase = (
        f"{nome} ({periodo(df)}), {c.fmt_int(t[c.M_MOV])} movimentações deixaram saldo de "
        f"{c.fmt_int(t[c.M_SALDO])} vagas ({c.fmt_pct(t[c.M_SALDO_REL])} das movimentações): "
        f"{c.fmt_pct(t[c.M_GIRO])} das contratações só repõem saídas e "
        f"{c.fmt_pct(t[c.M_SAIDA_VOL])} dos desligamentos são a pedido do trabalhador."
    )
    m = unidades(df, relevantes=True)
    if not m.empty:
        tensa = m.iloc[0]
        expansao = m[m[c.M_SALDO] > 0].sort_values("dinamismo", ascending=False)
        frase += (
            f" O apagão aparece como retenção: a maior tensão está em "
            f"**{tensa[c.COLUNA_SETOR]} – {tensa[c.COLUNA_REGIAO]}** ({tensa['motor']})"
        )
        if not expansao.empty:
            e = expansao.iloc[0]
            frase += (f", e a expansão mais acelerada em **{e[c.COLUNA_SETOR]} – "
                      f"{e[c.COLUNA_REGIAO]}** (saldo {c.fmt_int(e[c.M_SALDO])})")
        frase += "."
    return frase


def _filtro_unidade(regiao: str, setor: str | None = None, macro: str | None = None) -> dict:
    filtros = {"f_nivel": c.NIVEL_MESO, "f_terr": [regiao]}
    if setor:
        filtros["f_setor"] = [setor]
    if macro:
        filtros["f_macro"] = [macro]
    return filtros


def principais_achados(df: pd.DataFrame, limite: int = 5) -> list[Achado]:
    """3–5 achados ranqueados pela força do sinal (|z|), cada um com seus filtros."""
    if df is None or df.empty:
        return []
    ref = c.total(df)
    m = unidades(df, relevantes=True)
    achados: list[Achado] = []
    if not m.empty:
        u = m.iloc[0]
        achados.append(Achado(
            "Maior tensão",
            f"**{u[c.COLUNA_SETOR]}** em **{u[c.COLUNA_REGIAO]}**: saída voluntária "
            f"{c.fmt_pct(u[c.M_SAIDA_VOL])} (estado: {c.fmt_pct(ref[c.M_SAIDA_VOL])}), gap salarial "
            f"{c.fmt_razao(u[c.M_GAP_SAL])}, n = {c.fmt_int(u[c.M_MOV])}. Motor: {u['motor']}.",
            _filtro_unidade(u[c.COLUNA_REGIAO], u[c.COLUNA_SETOR]), float(u["tensao"]),
        ))
        exp = m[m[c.M_SALDO] > 0].sort_values("dinamismo", ascending=False)
        if not exp.empty:
            e = exp.iloc[0]
            achados.append(Achado(
                "Expansão mais acelerada",
                f"**{e[c.COLUNA_SETOR]}** em **{e[c.COLUNA_REGIAO]}**: saldo {c.fmt_int(e[c.M_SALDO])} "
                f"({c.fmt_pct(e[c.M_SALDO_REL])} das movimentações), aceleração {c.fmt_pp(e[c.M_ACEL])} "
                f"entre semestres, n = {c.fmt_int(e[c.M_MOV])}.",
                _filtro_unidade(e[c.COLUNA_REGIAO], e[c.COLUNA_SETOR]), float(e["dinamismo"]),
            ))
        comp = m.dropna(subset=[c.M_GAP_SAL]).sort_values(c.M_GAP_SAL)
        if not comp.empty and comp.iloc[0][c.M_GAP_SAL] < c.LIMIAR_COMPRESSAO:
            k = comp.iloc[0]
            achados.append(Achado(
                "Maior compressão salarial",
                f"**{k[c.COLUNA_SETOR]}** em **{k[c.COLUNA_REGIAO]}**: quem entra ganha "
                f"{c.fmt_pct(k[c.M_GAP_SAL], 0)} do salário de quem sai "
                f"({c.fmt_brl(k[c.M_SAL_ADM])} vs {c.fmt_brl(k[c.M_SAL_DESL])}), n = {c.fmt_int(k[c.M_MOV])}.",
                _filtro_unidade(k[c.COLUNA_REGIAO], k[c.COLUNA_SETOR]), float(abs(k["z_compressao"])),
            ))
    macros = c.agregar_metricas(df, [c.COLUNA_MACROFAMILIA_CBO])
    piso = max(c.MIN_MOVIMENTACOES, FRACAO_RELEVANCIA * float(macros[c.M_MOV].sum()))
    macros = macros[(macros[c.M_MOV] >= piso)
                    & (macros[c.COLUNA_MACROFAMILIA_CBO].astype(str) != c.NAO_CLASSIFICADO)
                    ].dropna(subset=[c.M_SAIDA_VOL])
    if len(macros) >= 2:
        z = c.zscore(macros[c.M_SAIDA_VOL])
        topo = macros.loc[macros[c.M_SAIDA_VOL].idxmax()]
        achados.append(Achado(
            "Ocupação que mais pede demissão (IA)",
            f"A macrofamília **{topo[c.COLUNA_MACROFAMILIA_CBO]}** tem a maior saída voluntária: "
            f"{c.fmt_pct(topo[c.M_SAIDA_VOL])} dos desligamentos, n = {c.fmt_int(topo[c.M_MOV])}.",
            {"f_macro": [str(topo[c.COLUNA_MACROFAMILIA_CBO])]}, float(z.max()),
        ))
        esc = macros.dropna(subset=[c.M_GAP_ESC]).sort_values(c.M_GAP_ESC)
        if not esc.empty and esc.iloc[0][c.M_GAP_ESC] < 0:
            q = esc.iloc[0]
            achados.append(Achado(
                "Contratação com menos estudo",
                f"Em **{q[c.COLUNA_MACROFAMILIA_CBO]}**, os admitidos têm "
                f"{c.fmt_num(abs(q[c.M_GAP_ESC]), 2)} nível de escolaridade a menos que os desligados "
                f"(n = {c.fmt_int(q[c.M_MOV])}).",
                {"f_macro": [str(q[c.COLUNA_MACROFAMILIA_CBO])]},
                float(abs(c.zscore(macros[c.M_GAP_ESC]).loc[q.name])) if len(macros) > 1 else 0.0,
            ))
    # Um mesmo recorte não aparece duas vezes (ex.: maior tensão = maior compressão).
    unicos, vistos = [], set()
    for achado in sorted(achados, key=lambda a: a.forca, reverse=True):
        chave = tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in achado.filtros.items()))
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(achado)
    return unicos[:limite]


def legenda_serie(mensal: pd.DataFrame) -> str:
    """Legenda de uma linha da série mensal: melhor e pior mês de saldo."""
    if mensal is None or mensal.empty:
        return ""
    melhor = mensal.loc[mensal[c.M_SALDO].idxmax()]
    pior = mensal.loc[mensal[c.M_SALDO].idxmin()]
    return (f"Melhor mês: {c.rotulo_mes(melhor[c.COLUNA_MES])} (saldo {c.fmt_int(melhor[c.M_SALDO])}); "
            f"pior: {c.rotulo_mes(pior[c.COLUNA_MES])} (saldo {c.fmt_int(pior[c.M_SALDO])}). "
            "Dezembro concentra desligamentos sazonais.")


def legenda_mapa(metricas: pd.DataFrame, metrica: str, rotulo: str) -> str:
    """Legenda do mapa: a unidade com o valor mais extremo (com amostra)."""
    validas = metricas[metricas[c.M_AMOSTRA_OK]].dropna(subset=[metrica])
    if validas.empty:
        return "Nenhuma unidade com amostra suficiente (≥ 100 movimentações)."
    tensao = metrica in (c.M_SAIDA_VOL, c.M_GIRO)
    extremo = validas.loc[validas[metrica].idxmax() if tensao or metrica != c.M_GAP_SAL else validas[metrica].idxmin()]
    definicao = c.DEFINICOES[metrica]
    return (f"{'Maior' if tensao or metrica != c.M_GAP_SAL else 'Menor'} {definicao.rotulo.lower()}: "
            f"**{extremo[rotulo]}** ({c.fmt_metrica(metrica, extremo[metrica])}, n = {c.fmt_int(extremo[c.M_MOV])}). "
            f"Cinza = amostra insuficiente.")
