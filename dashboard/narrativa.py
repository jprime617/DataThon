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
    texto = (f"Melhor mês: {c.rotulo_mes(melhor[c.COLUNA_MES])} (saldo {c.fmt_int(melhor[c.M_SALDO])}); "
             f"pior: {c.rotulo_mes(pior[c.COLUNA_MES])} (saldo {c.fmt_int(pior[c.M_SALDO])}).")
    # BUG-03: a nota sazonal só vale quando o pior mês é mesmo dezembro.
    if str(pior[c.COLUNA_MES]).endswith("12") and pior[c.M_SALDO] < 0:
        texto += " Dezembro concentra desligamentos sazonais."
    return texto


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


def _lista(itens: list[str]) -> str:
    """["a", "b", "c"] → "a, b e c"."""
    return ", ".join(itens[:-1]) + " e " + itens[-1] if len(itens) > 1 else "".join(itens)


# --- DATA-01: onde se concentra um gap de escolaridade fora da curva -----------

def destaque_escolaridade(df: pd.DataFrame, perfil: pd.DataFrame | None = None) -> str | None:
    """Nota sobre a macrofamília com gap de escolaridade ≤ `LIMIAR_DESTAQUE_GAP_ESC`.

    Diz onde as admissões dela se concentram (mesorregião e municípios) e, com o
    perfil, quanto dos admitidos e dos desligados tem até o fundamental
    incompleto. ``None`` quando nenhuma macrofamília passa do limiar.
    """
    if df is None or df.empty:
        return None
    macros = c.agregar_metricas(df, [c.COLUNA_MACROFAMILIA_CBO])
    macros = macros[macros[c.M_AMOSTRA_OK]
                    & (macros[c.COLUNA_MACROFAMILIA_CBO].astype(str) != c.NAO_CLASSIFICADO)].dropna(subset=[c.M_GAP_ESC])
    if macros.empty:
        return None
    pior = macros.loc[macros[c.M_GAP_ESC].idxmin()]
    if pior[c.M_GAP_ESC] > c.LIMIAR_DESTAQUE_GAP_ESC:
        return None
    nome = str(pior[c.COLUNA_MACROFAMILIA_CBO])
    demais = macros[macros[c.COLUNA_MACROFAMILIA_CBO].astype(str) != nome][c.M_GAP_ESC]
    sub = df[df[c.COLUNA_MACROFAMILIA_CBO].astype(str) == nome]
    regioes = c.agregar_metricas(sub, [c.COLUNA_REGIAO])
    adm_total = float(regioes[c.COLUNA_ADMISSOES].sum()) or 1.0
    topo = regioes.sort_values(c.COLUNA_ADMISSOES, ascending=False).iloc[0]
    regiao = str(topo[c.COLUNA_REGIAO])
    municipios = (sub[sub[c.COLUNA_REGIAO].astype(str) == regiao]
                  .groupby(c.COLUNA_NOME_MUNICIPIO, observed=True)[c.COLUNA_ADMISSOES].sum()
                  .sort_values(ascending=False).head(3).index.astype(str).tolist())
    texto = (f"**{nome}** destoa: quem entra tem {c.fmt_num(-pior[c.M_GAP_ESC], 2)} nível de escolaridade "
             f"a menos que quem sai")
    if not demais.empty:
        texto += (f" (nas demais macrofamílias, entre {c.fmt_num(demais.min(), 2)} e "
                  f"{c.fmt_num(demais.max(), 2)})")
    texto += (f". {c.fmt_pct(topo[c.COLUNA_ADMISSOES] / adm_total, 0)} das admissões estão em **{regiao}** "
              f"(gap {c.fmt_num(topo[c.M_GAP_ESC], 2)}), sobretudo em {_lista(municipios)}.")
    if perfil is not None and not perfil.empty:
        p = perfil[perfil[c.COLUNA_MACROFAMILIA_CBO].astype(str) == nome]
        baixa = p[c.COLUNA_FAIXA_ESCOLARIDADE].astype(str) == "Até fundamental incompleto"
        adm, desl = p[c.COLUNA_ADMISSOES].sum(), p[c.COLUNA_DESLIGAMENTOS].sum()
        if adm > 0 and desl > 0:
            texto += (f" Até o fundamental incompleto: {c.fmt_pct(p.loc[baixa, c.COLUNA_ADMISSOES].sum() / adm)} "
                      f"dos admitidos e {c.fmt_pct(p.loc[baixa, c.COLUNA_DESLIGAMENTOS].sum() / desl)} dos "
                      "desligados (período inteiro).")
    return texto + " O dado é real (códigos fora da escala 1–11 ficam fora da média); a causa pede investigação local."


# --- BUG-02: funil do pipeline, cada queda com o motivo -------------------------

@dataclass
class EtapaFunil:
    rotulo: str
    valor: int
    perda: int = 0       # quanto saiu em relação à etapa anterior
    motivo: str = ""     # por que saiu


def etapas_funil(linhas: dict) -> list[EtapaFunil]:
    """Etapas do funil do pipeline (de cima para baixo, na ordem do processo).

    As linhas lidas são MOV + FOR + EXC. Cada linha EXC (exclusão declarada)
    sai e anula a declaração que ela corrige: a queda entre as linhas no período
    e as movimentações é 2 × EXC. Com ``por_tipo`` nos metadados, o funil confere
    essa conta; a diferença que sobrar aparece como "outras perdas", nunca some.
    """
    if not linhas:
        return []
    brutas = int(linhas.get("brutas", 0))
    fora = int(linhas.get("excluidas_competencia", 0))
    no_periodo = int(linhas.get("apos_limpeza", brutas - fora))
    movs = int(linhas.get("movimentacoes_agregadas", 0))
    industria = int(linhas.get("movimentacoes_industria", 0))
    por_tipo = linhas.get("por_tipo") or {}
    etapas = [EtapaFunil("Linhas lidas do CAGED (SC)", brutas, 0,
                         "MOV + FOR + EXC" if por_tipo else "")]
    etapas.append(EtapaFunil("No período analisado", no_periodo, brutas - no_periodo, "fora do período"))
    perda = no_periodo - movs
    if "EXC" in por_tipo:
        exc = int(por_tipo["EXC"])
        motivo = f"{c.fmt_int(exc)} exclusões declaradas (EXC), cada uma anulando a declaração que corrige"
        if perda != 2 * exc:
            motivo += f"; outras perdas: {c.fmt_int(perda - 2 * exc)}"
    else:
        motivo = "exclusões declaradas (EXC) e as declarações que elas anulam"
    etapas.append(EtapaFunil("Movimentações válidas", movs, perda, motivo))
    etapas.append(EtapaFunil("Movimentações da indústria (seções B–F)", industria, movs - industria,
                             "movimentações de outras seções (agro, comércio, serviços, governo)"))
    return etapas


def texto_funil(etapas: list[EtapaFunil]) -> str:
    """Uma frase por queda do funil, com o número e o motivo (nada escrito à mão)."""
    if not etapas:
        return ""
    frases = [f"{c.fmt_int(etapas[0].valor)} linhas lidas"
              + (f" ({etapas[0].motivo})" if etapas[0].motivo else "") + "."]
    for e in etapas[1:]:
        destino = e.rotulo[0].lower() + e.rotulo[1:]
        if e.perda:
            frases.append(f"Saem {c.fmt_int(e.perda)}: {e.motivo} → {c.fmt_int(e.valor)} {destino}.")
        else:
            frases.append(f"Nenhuma linha {e.motivo}.")
    if len(etapas) > 1 and etapas[-2].valor:
        frases[-1] = frases[-1][:-1] + f", {c.fmt_pct(etapas[-1].valor / etapas[-2].valor)} das movimentações válidas."
    return " ".join(frases)
