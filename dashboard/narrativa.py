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
    """A pergunta de negócio respondida em Markdown: uma manchete e 4 tópicos.

    A manchete interpretativa ("o apagão é de retenção") só aparece quando os
    números a sustentam: o saldo é pequeno diante do volume (|saldo| ≤ 5% das
    movimentações) e ao menos 40% dos desligamentos são a pedido.
    """
    if df is None or df.empty:
        return "Nenhuma movimentação na seleção atual — ajuste ou limpe os filtros."
    t = c.total(df)
    nome = "A indústria catarinense" if escopo == c.ESCOPO_INDUSTRIA else "A economia catarinense"
    if abs(t[c.M_SALDO_REL]) <= 0.05 and t[c.M_SAIDA_VOL] >= 0.4:
        manchete = (f"{nome} ({periodo(df)}) movimenta muito e cresce pouco: "
                    "o apagão é de retenção, não de falta de contratação.")
    else:
        manchete = f"{nome} ({periodo(df)}) em quatro números."
    topicos = [
        f"**{c.fmt_int(t[c.M_MOV])} movimentações** deixaram saldo de {c.fmt_int(t[c.M_SALDO])} vagas "
        f"({c.fmt_pct(t[c.M_SALDO_REL])} do total).",
        f"**{c.fmt_pct(t[c.M_SAIDA_VOL])}** dos desligamentos são a pedido do trabalhador.",
    ]
    m = unidades(df, relevantes=True)
    if not m.empty:
        tensa = m.iloc[0]
        topicos.append(f"Maior tensão: **{tensa[c.COLUNA_SETOR]} – {tensa[c.COLUNA_REGIAO]}** ({tensa['motor']}).")
        expansao = m[m[c.M_SALDO] > 0].sort_values("dinamismo", ascending=False)
        if not expansao.empty:
            e = expansao.iloc[0]
            topicos.append(f"Expansão mais acelerada: **{e[c.COLUNA_SETOR]} – {e[c.COLUNA_REGIAO]}** "
                           f"(saldo {c.fmt_int(e[c.M_SALDO])}).")
    return f"{manchete}\n\n" + "\n".join(f"- {t_}" for t_ in topicos)


def _filtro_unidade(regiao: str, setor: str | None = None, macro: str | None = None) -> dict:
    filtros = {"f_nivel": c.NIVEL_MESO, "f_terr": [regiao]}
    if setor:
        filtros["f_setor"] = [setor]
    if macro:
        filtros["f_macro"] = [macro]
    return filtros


def _sintomas(u: pd.Series, ref: pd.Series) -> str:
    """Os sintomas de tensão da unidade contra o estado, do mais forte (z) ao mais fraco."""
    partes = []
    for nome in sorted(c.PESOS_TENSAO_PADRAO, key=lambda n: -float(u.get(f"z_{n}", float("-inf")) or 0)):
        if pd.notna(u.get(nome)):
            rotulo = c.DEFINICOES[nome].rotulo.lower()
            partes.append(f"{rotulo} {c.fmt_pct(u[nome])} (estado: {c.fmt_pct(ref[nome])})")
    return ", ".join(partes)


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
            f"**{u[c.COLUNA_SETOR]}** em **{u[c.COLUNA_REGIAO]}**: {_sintomas(u, ref)}; quem entra ganha "
            f"{c.fmt_gap(u[c.M_GAP_SAL])} de quem saiu ({c.fmt_int(u[c.M_MOV])} movimentações).",
            _filtro_unidade(u[c.COLUNA_REGIAO], u[c.COLUNA_SETOR]), float(u["tensao"]),
        ))
        exp = m[m[c.M_SALDO] > 0].sort_values("dinamismo", ascending=False)
        if not exp.empty:
            e = exp.iloc[0]
            achados.append(Achado(
                "Expansão mais acelerada",
                f"**{e[c.COLUNA_SETOR]}** em **{e[c.COLUNA_REGIAO]}**: saldo {c.fmt_int(e[c.M_SALDO])}"
                + (f"; o emprego cresceu {c.fmt_pct(e[c.M_VAR_REL])} no ano, "
                   f"{c.fmt_num(abs(e[c.M_ACEL]), 1)} pontos {'a mais' if e[c.M_ACEL] >= 0 else 'a menos'} "
                   "que no ano anterior."
                   if pd.notna(e[c.M_VAR_REL]) and pd.notna(e[c.M_ACEL])
                   else f" ({c.fmt_pct(e[c.M_SALDO_REL])} das movimentações)."),
                _filtro_unidade(e[c.COLUNA_REGIAO], e[c.COLUNA_SETOR]), float(e["dinamismo"]),
            ))
        z_comp = c.zscore(1 - m[c.M_GAP_SAL])
        comp = m.dropna(subset=[c.M_GAP_SAL]).sort_values(c.M_GAP_SAL)
        if not comp.empty and comp.iloc[0][c.M_GAP_SAL] < c.LIMIAR_COMPRESSAO:
            k = comp.iloc[0]
            achados.append(Achado(
                "Maior compressão salarial",
                f"**{k[c.COLUNA_SETOR]}** em **{k[c.COLUNA_REGIAO]}**: quem entra ganha "
                f"{c.fmt_pct(k[c.M_GAP_SAL], 0)} do salário de quem sai "
                f"({c.fmt_brl(k[c.M_SAL_ADM])} contra {c.fmt_brl(k[c.M_SAL_DESL])}).",
                _filtro_unidade(k[c.COLUNA_REGIAO], k[c.COLUNA_SETOR]), float(abs(z_comp[k.name])),
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
            f"{c.fmt_pct(topo[c.M_SAIDA_VOL])} de quem sai pede para sair.",
            {"f_macro": [str(topo[c.COLUNA_MACROFAMILIA_CBO])]}, float(z.max()),
        ))
        esc = macros.dropna(subset=[c.M_GAP_ESC]).sort_values(c.M_GAP_ESC)
        if not esc.empty and esc.iloc[0][c.M_GAP_ESC] < 0:
            q = esc.iloc[0]
            achados.append(Achado(
                "Contratação com menos estudo",
                f"Em **{q[c.COLUNA_MACROFAMILIA_CBO]}**, quem é contratado estudou menos, em média, "
                "do que quem saiu.",
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


# Como ler a cor de cada indicador do mapa, em linguagem leiga.
LEITURA_MAPA = {
    c.M_SALDO_10K: "Azul = abriu vagas; laranja = fechou vagas (conta por 10 mil habitantes).",
    c.M_SALDO_REL: "Azul = abriu vagas; laranja = fechou vagas.",
    c.M_ROT_DESC: "Quanto mais escuro, mais a equipe é trocada ao longo do ano.",
    c.M_SAIDA_VOL: "Quanto mais escuro, mais gente pede para sair.",
    c.M_GAP_SAL: "Verde = quem entra ganha mais do que quem saiu; marrom = ganha menos.",
    c.M_GAP_ESC: "Verde = quem entra estudou mais do que quem saiu; roxo = estudou menos.",
}
_MENOR_E_PIOR = {c.M_GAP_SAL, c.M_GAP_ESC, c.M_SALDO_10K, c.M_SALDO_REL}


def legenda_mapa(metricas: pd.DataFrame, metrica: str, rotulo: str) -> str:
    """Legenda do mapa: como ler a cor e a unidade em pior situação (com amostra)."""
    leitura = LEITURA_MAPA.get(metrica, "")
    validas = metricas[metricas[c.M_AMOSTRA_OK]].dropna(subset=[metrica])
    if validas.empty:
        return f"{leitura} Nenhuma região com dados suficientes nesta seleção.".strip()
    pior = metrica in _MENOR_E_PIOR
    extremo = validas.loc[validas[metrica].idxmin() if pior else validas[metrica].idxmax()]
    definicao = c.DEFINICOES[metrica]
    return (f"{leitura} Pior situação: **{extremo[rotulo]}** "
            f"({definicao.rotulo.lower()}: {c.fmt_metrica(metrica, extremo[metrica])}). "
            f"Cinza = poucos dados.")


# --- Panorama: legenda do mapa, sinais e guia de decisão -----------------------

# Os dois polos de cada indicador do mapa (topo e base da legenda), em linguagem leiga.
POLOS_MAPA = {
    c.M_SALDO_10K: ("Abriu mais vagas", "Fechou mais vagas"),
    c.M_SALDO_REL: ("Abriu mais vagas", "Fechou mais vagas"),
    c.M_ROT_DESC: ("Troca mais a equipe", "Troca menos a equipe"),
    c.M_SAIDA_VOL: ("Mais gente pede para sair", "Menos gente pede para sair"),
    c.M_GAP_SAL: ("Quem entra ganha mais que quem saiu", "Quem entra ganha menos que quem saiu"),
    c.M_GAP_ESC: ("Quem entra estudou mais", "Quem entra estudou menos"),
}
# A unidade dos números da legenda.
UNIDADE_LEGENDA = {
    c.M_SALDO_10K: "Saldo de vagas por 10 mil habitantes.",
    c.M_SALDO_REL: "Saldo em % do total movimentado.",
    c.M_ROT_DESC: "% da equipe trocada no período.",
    c.M_SAIDA_VOL: "% dos desligamentos que foram a pedido.",
    c.M_GAP_SAL: "Salário de quem entra, em % do de quem saiu (100% = igual).",
    c.M_GAP_ESC: "Diferença de escolaridade, em níveis.",
}


def extremos_mapa(metricas: pd.DataFrame, metrica: str, rotulo: str, n: int = 3) -> tuple[list, list]:
    """(piores, melhores): as `n` unidades em pior e em melhor situação, como (nome, valor formatado)."""
    unidades = metricas.drop_duplicates(rotulo)
    validas = unidades[unidades[c.M_AMOSTRA_OK]].dropna(subset=[metrica])
    if validas.empty:
        return [], []
    ordem = validas.sort_values(metrica, ascending=metrica in _MENOR_E_PIOR, kind="stable")
    par = lambda d: [(str(r), c.fmt_metrica(metrica, v)) for r, v in zip(d[rotulo], d[metrica])]  # noqa: E731
    return par(ordem.head(n)), par(ordem.tail(n).iloc[::-1])


@dataclass
class Sinal:
    """Um conceito-chave do Panorama: o que é, quanto vale no recorte e se acende o alerta."""

    metrica: str          # a métrica que o botão "ver no mapa" escolhe
    titulo: str
    o_que_e: str
    valor: str
    referencia: str
    alerta: bool
    leitura: str


LIMIAR_SAIDA_VOLUNTARIA = 0.40  # o mesmo da manchete: a partir daqui o apagão é de retenção
MARGEM_ALERTA = 0.05            # com recorte: 5 p.p. acima do estado (mesma régua das causas)


def sinais(t: pd.Series, ref: pd.Series | None = None) -> list[Sinal]:
    """Os quatro sinais do Panorama, cada um com a referência que decide o alerta.

    Sem recorte (``ref=None``) a referência é fixa: rotatividade oficial de SC
    (MTE), 40% de saída voluntária e o limiar de compressão salarial. Com
    recorte, rotatividade e saída voluntária se comparam ao estado (+5 p.p.).
    """
    saldo, mov, saldo_rel = t[c.M_SALDO], t[c.M_MOV], t[c.M_SALDO_REL]
    if saldo < 0:
        leitura_saldo = "Fechou mais vagas do que abriu."
    elif saldo == 0:
        leitura_saldo = "Abriu e fechou o mesmo número de vagas."
    elif saldo_rel <= 0.05:
        leitura_saldo = f"Cresce pouco: {c.fmt_int(mov / saldo)} contratações e saídas para cada vaga nova."
    else:
        leitura_saldo = "Cresce com folga: o saldo passa de 5% de tudo o que movimenta."
    lista = [Sinal(
        c.M_SALDO_10K, "Saldo de vagas", "Contratações menos desligamentos: o emprego cresceu ou encolheu?",
        f"{c.fmt_int(saldo)} vagas",
        f"{c.fmt_metrica(c.M_SALDO_10K, t[c.M_SALDO_10K])} por 10 mil hab. · {c.fmt_int(mov)} movimentações",
        pd.isna(saldo_rel) or saldo_rel <= 0.05, leitura_saldo,
    )]

    rot = t[c.M_ROT_DESC]
    if ref is not None and pd.notna(ref[c.M_ROT_DESC]):
        texto_ref, limite = f"Santa Catarina: {c.fmt_pct(ref[c.M_ROT_DESC])}", ref[c.M_ROT_DESC] + MARGEM_ALERTA
    else:
        oficial = c.ROTATIVIDADE_OFICIAL
        texto_ref = f"Oficial (MTE): SC {c.fmt_pct(oficial['SC'])} · Brasil {c.fmt_pct(oficial['Brasil'])}"
        limite = oficial["SC"]
    lista.append(Sinal(
        c.M_ROT_DESC, "Troca de equipe", "Rotatividade: quanto da equipe é substituída no período.",
        c.fmt_pct(rot), texto_ref, pd.notna(rot) and rot > limite,
        f"De cada 100 postos, cerca de {round(rot * 100)} trocaram de ocupante." if pd.notna(rot)
        else "Sem o estoque da RAIS para este recorte.",
    ))

    saida = t[c.M_SAIDA_VOL]
    if ref is not None and pd.notna(ref[c.M_SAIDA_VOL]):
        texto_ref, limite = f"Santa Catarina: {c.fmt_pct(ref[c.M_SAIDA_VOL])}", ref[c.M_SAIDA_VOL] + MARGEM_ALERTA
    else:
        texto_ref, limite = f"Alerta a partir de {c.fmt_pct(LIMIAR_SAIDA_VOLUNTARIA, 0)}", LIMIAR_SAIDA_VOLUNTARIA
    lista.append(Sinal(
        c.M_SAIDA_VOL, "Pedem para sair", "Saída voluntária: desligamentos a pedido do próprio trabalhador.",
        c.fmt_pct(saida), texto_ref, pd.notna(saida) and saida >= limite,
        f"{round(saida * 100)} de cada 100 desligamentos foram escolha de quem saiu." if pd.notna(saida)
        else "Sem desligamentos neste recorte.",
    ))

    gap = t[c.M_GAP_SAL]
    compressao = c.fmt_gap(c.LIMIAR_COMPRESSAO)
    texto_ref = f"Alerta quando fica {compressao} ou mais" + (
        f" · Santa Catarina: {c.fmt_gap(ref[c.M_GAP_SAL])}" if ref is not None and pd.notna(ref[c.M_GAP_SAL]) else "")
    ok = bool(t.get(c.M_SALARIO_OK, True)) and pd.notna(gap)
    lista.append(Sinal(
        c.M_GAP_SAL, "Salário de quem entra", "O contratado ganha mais ou menos do que quem saiu da vaga?",
        c.fmt_gap(gap) if ok else "—", texto_ref, ok and gap < c.LIMIAR_COMPRESSAO,
        (f"Quem entra ganha {c.fmt_gap(gap)} do salário de quem saiu: "
         + ("a vaga ficou menos atraente." if gap < c.LIMIAR_COMPRESSAO else "o salário não explica a saída."))
        if ok else "Poucos salários para comparar neste recorte.",
    ))
    return lista


# Situação de cada grupo (quadrante da matriz) → como é e o que fazer primeiro.
# As ações são as alavancas do motor de recomendações (`comum.gerar_recomendacoes`).
GUIA_QUADRANTES = {
    c.Q_APAGAO: ("Perde gente e quase não cresce.",
                 "Estancar a saída antes de contratar mais: rever o salário de entrada e reter quem já está."),
    c.Q_PRESSAO: ("Cresce, mas perde gente no caminho.",
                  "Sustentar o crescimento: formação técnica e recrutamento em outras regiões."),
    c.Q_ESTAGNACAO: ("Segura a equipe, mas não cresce.",
                     "Acompanhar e rever postos de nível básico (automação e redesenho de funções)."),
    c.Q_SAUDAVEL: ("Cresce e segura a equipe.",
                   "Manter e usar como referência de boas práticas para os demais."),
}


def resumo_quadrantes(m: pd.DataFrame) -> dict[str, tuple[int, float]]:
    """Quadrante → (nº de grupos, fração das movimentações analisadas)."""
    if m is None or m.empty:
        return {q: (0, 0.0) for q in GUIA_QUADRANTES}
    total_mov = float(m[c.M_MOV].sum()) or 1.0
    return {q: (int((m["quadrante"] == q).sum()), float(m.loc[m["quadrante"] == q, c.M_MOV].sum()) / total_mov)
            for q in GUIA_QUADRANTES}
