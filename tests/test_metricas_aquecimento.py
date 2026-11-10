"""Teste de propriedade do Indice_de_Aquecimento do Calculador_de_Metricas (tarefa 7.8).

Valida, com Hypothesis (mín. 100 exemplos), a métrica composta de
`src/metricas.py`:

- Property 18: `Indice_de_Aquecimento` é a soma de nível e variação mensal
  (R4.8, R4.9). Para qualquer série mensal de um recorte, o
  `Indice_de_Aquecimento` de um mês é igual ao `Saldo_por_10k` daquele mês mais
  a diferença de `Saldo_Liquido` em relação ao mês imediatamente anterior da
  série; a componente de variação é zero no primeiro mês de cada recorte (R4.9).

LLM e Azure não entram aqui: a função sob teste é pura sobre DataFrames.
"""

from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.metricas import (
    COLUNA_CHAVE_MUNICIPAL,
    COLUNA_COMPETENCIA,
    COLUNA_INDICE_AQUECIMENTO,
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_POR_10K,
    COLUNA_VARIACAO_MENSAL,
    indice_aquecimento,
)

# ---------------------------------------------------------------------------
# Estratégias
# ---------------------------------------------------------------------------

# Poucos recortes distintos (município × seção) para forçar múltiplas séries reais.
_chaves_municipais = st.sampled_from(["420010", "420020", "420030"])
_secoes = st.sampled_from(["A", "B", "C"])

# Competências mensais no formato AAAAMM, dentro do período do projeto.
_competencias = st.sampled_from(
    [202509, 202510, 202511, 202512, 202601, 202602, 202603, 202604]
)

# Saldos líquidos arbitrários (podem ser negativos, zero ou positivos).
_saldos = st.integers(min_value=-5_000, max_value=5_000)

# Saldo_por_10k: float (a métrica de nível pode ser qualquer real finito).
_saldos_por_10k = st.floats(
    min_value=-50_000.0,
    max_value=50_000.0,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def _serie_mensal_por_recorte(draw: st.DrawFn) -> pd.DataFrame:
    """Gera um DataFrame mensal de saldos por recorte (município × seção).

    Garante **unicidade** de (recorte, competência) — uma linha por mês de cada
    série — exatamente como a saída de `saldo_por_10k` sobre um recorte mensal.
    Pode ser vazio, para exercitar o caso sem séries (R4.9), e embaralha as
    linhas para provar que a função ordena internamente antes de calcular a
    variação.
    """
    n_recortes = draw(st.integers(min_value=0, max_value=4))
    recortes = draw(
        st.lists(
            st.tuples(_chaves_municipais, _secoes),
            min_size=n_recortes,
            max_size=n_recortes,
            unique=True,
        )
    )

    linhas: list[dict[str, object]] = []
    for chave, secao in recortes:
        # Para cada recorte, escolhe um subconjunto de meses distintos.
        meses = draw(
            st.lists(_competencias, min_size=1, max_size=8, unique=True)
        )
        for competencia in meses:
            linhas.append(
                {
                    COLUNA_CHAVE_MUNICIPAL: chave,
                    "seção": secao,
                    COLUNA_COMPETENCIA: competencia,
                    COLUNA_SALDO_LIQUIDO: draw(_saldos),
                    COLUNA_SALDO_POR_10K: draw(_saldos_por_10k),
                }
            )

    colunas = [
        COLUNA_CHAVE_MUNICIPAL,
        "seção",
        COLUNA_COMPETENCIA,
        COLUNA_SALDO_LIQUIDO,
        COLUNA_SALDO_POR_10K,
    ]
    if not linhas:
        return pd.DataFrame(columns=colunas)

    df = pd.DataFrame(linhas, columns=colunas)
    # Embaralha para garantir que a função não dependa da ordem de entrada.
    ordem = draw(st.permutations(list(df.index)))
    return df.loc[list(ordem)].reset_index(drop=True)


def _variacao_esperada(df: pd.DataFrame) -> dict[tuple, float]:
    """Calcula a variação mensal esperada de forma independente.

    Para cada recorte (chave_municipal × seção), ordena por competência crescente
    e computa Saldo_Liquido(mês) − Saldo_Liquido(mês anterior); o primeiro mês da
    série recebe 0 (R4.9). Retorna um mapa (chave, seção, competência) → variação.
    """
    esperado: dict[tuple, float] = {}
    chaves_recorte = df[[COLUNA_CHAVE_MUNICIPAL, "seção"]].drop_duplicates()
    for _, rec in chaves_recorte.iterrows():
        chave = rec[COLUNA_CHAVE_MUNICIPAL]
        secao = rec["seção"]
        serie = df[
            (df[COLUNA_CHAVE_MUNICIPAL] == chave) & (df["seção"] == secao)
        ].sort_values(COLUNA_COMPETENCIA)
        anterior: float | None = None
        for _, linha in serie.iterrows():
            saldo = float(linha[COLUNA_SALDO_LIQUIDO])
            variacao = 0.0 if anterior is None else saldo - anterior
            esperado[(chave, secao, linha[COLUNA_COMPETENCIA])] = variacao
            anterior = saldo
    return esperado


# ---------------------------------------------------------------------------
# Property 18
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 18: Indice_de_Aquecimento é a soma de nível e variação mensal
@given(df=_serie_mensal_por_recorte())
@settings(max_examples=100)
def test_prop18_indice_aquecimento_e_soma_de_nivel_e_variacao(
    df: pd.DataFrame,
) -> None:
    """`indice_aquecimento = saldo_por_10k + variacao_mensal` por mês e recorte.

    - A variação mensal é Saldo_Liquido(mês) − Saldo_Liquido(mês anterior) dentro
      de cada recorte, calculada de forma independente (R4.8).
    - O primeiro mês de cada série não tem mês anterior → variação 0 (R4.9).
    - O índice é exatamente a soma do nível (`saldo_por_10k`) com a variação; as
      linhas e a ordem da entrada são preservadas.

    Validates: Requirements 4.8, 4.9
    """
    resultado = indice_aquecimento(df)

    # Preserva linhas, ordem e acrescenta as colunas de variação e índice.
    assert len(resultado) == len(df)
    assert COLUNA_VARIACAO_MENSAL in resultado.columns
    assert COLUNA_INDICE_AQUECIMENTO in resultado.columns

    if df.empty:
        assert resultado.empty
        return

    esperado = _variacao_esperada(df)

    for _, linha in resultado.iterrows():
        chave = linha[COLUNA_CHAVE_MUNICIPAL]
        secao = linha["seção"]
        competencia = linha[COLUNA_COMPETENCIA]

        # Variação mensal bate com o cálculo independente (R4.8, R4.9).
        variacao_obtida = linha[COLUNA_VARIACAO_MENSAL]
        assert math.isclose(
            variacao_obtida,
            esperado[(chave, secao, competencia)],
            rel_tol=1e-9,
            abs_tol=1e-9,
        )

        # Índice é a soma de nível e variação (R4.8).
        soma = linha[COLUNA_SALDO_POR_10K] + variacao_obtida
        assert math.isclose(
            linha[COLUNA_INDICE_AQUECIMENTO], soma, rel_tol=1e-9, abs_tol=1e-9
        )


# Feature: datathon-caged-sc-pipeline, Property 18: Indice_de_Aquecimento é a soma de nível e variação mensal
@given(data=st.data())
@settings(max_examples=100)
def test_prop18_primeiro_mes_da_serie_tem_variacao_zero(
    data: st.DataObject,
) -> None:
    """O primeiro mês (menor competência) de cada recorte tem variação 0 (R4.9).

    Constrói uma única série mensal ordenada e verifica que, independentemente do
    saldo, a componente de variação do mês mais antigo é zero e o índice daquele
    mês é igual ao próprio `saldo_por_10k`.

    Validates: Requirements 4.8, 4.9
    """
    meses = data.draw(
        st.lists(_competencias, min_size=1, max_size=8, unique=True)
    )
    saldos = data.draw(
        st.lists(_saldos, min_size=len(meses), max_size=len(meses))
    )
    niveis = data.draw(
        st.lists(_saldos_por_10k, min_size=len(meses), max_size=len(meses))
    )

    df = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["420010"] * len(meses),
            COLUNA_COMPETENCIA: meses,
            COLUNA_SALDO_LIQUIDO: saldos,
            COLUNA_SALDO_POR_10K: niveis,
        }
    )

    resultado = indice_aquecimento(df)

    # O primeiro mês da série é o de menor competência.
    primeira_competencia = min(meses)
    primeira = resultado[
        resultado[COLUNA_COMPETENCIA] == primeira_competencia
    ].iloc[0]

    assert primeira[COLUNA_VARIACAO_MENSAL] == 0.0
    assert math.isclose(
        primeira[COLUNA_INDICE_AQUECIMENTO],
        primeira[COLUNA_SALDO_POR_10K],
        rel_tol=1e-9,
        abs_tol=1e-9,
    )


# Feature: datathon-caged-sc-pipeline, Property 18: Indice_de_Aquecimento é a soma de nível e variação mensal
@given(data=st.data())
@settings(max_examples=100)
def test_prop18_variacao_entre_meses_consecutivos_e_a_diferenca_de_saldo(
    data: st.DataObject,
) -> None:
    """Em meses consecutivos, a variação é a diferença de Saldo_Liquido (R4.8).

    Gera uma série ordenada e verifica, para cada mês a partir do segundo, que a
    variação reportada é exatamente Saldo_Liquido(mês) − Saldo_Liquido(mês
    anterior), e que a entrada embaralhada não altera o resultado.

    Validates: Requirements 4.8, 4.9
    """
    n = data.draw(st.integers(min_value=2, max_value=8))
    todas = [202509, 202510, 202511, 202512, 202601, 202602, 202603, 202604]
    meses = sorted(todas[:n])
    saldos = data.draw(st.lists(_saldos, min_size=n, max_size=n))
    niveis = data.draw(st.lists(_saldos_por_10k, min_size=n, max_size=n))

    df = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["420010"] * n,
            COLUNA_COMPETENCIA: meses,
            COLUNA_SALDO_LIQUIDO: saldos,
            COLUNA_SALDO_POR_10K: niveis,
        }
    )
    # Embaralha para provar independência da ordem de entrada.
    ordem = data.draw(st.permutations(list(df.index)))
    df = df.loc[list(ordem)].reset_index(drop=True)

    resultado = indice_aquecimento(df).sort_values(COLUNA_COMPETENCIA)

    saldos_por_mes = dict(zip(meses, saldos))
    variacoes = list(resultado[COLUNA_VARIACAO_MENSAL])
    competencias = list(resultado[COLUNA_COMPETENCIA])

    for i in range(1, len(competencias)):
        atual = saldos_por_mes[competencias[i]]
        anterior = saldos_por_mes[competencias[i - 1]]
        assert math.isclose(
            variacoes[i], atual - anterior, rel_tol=1e-9, abs_tol=1e-9
        )
