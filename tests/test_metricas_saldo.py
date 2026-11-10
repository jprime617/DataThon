"""Testes de propriedade de saldo do Calculador_de_Metricas (tarefa 7.2).

Valida, com Hypothesis (mín. 100 exemplos), as duas primeiras métricas de
`src/metricas.py`:

- Property 13: `Saldo_Liquido` é o balanço de admissões e desligamentos
  (R4.1, R4.10). Para qualquer conjunto de movimentações em um recorte, o saldo
  é igual ao nº de registros com `saldomovimentação == +1` menos o nº com
  `saldomovimentação == -1`; para o conjunto vazio é 0.
- Property 14: `Saldo_por_10k` segue a fórmula ou é ausente (R4.2, R4.3). Para
  qualquer saldo e população, o resultado é `(saldo / populacao) * 10_000`
  quando a população é maior que zero, e NaN quando a população é ausente
  (NaN/None) ou é zero/negativa.

LLM e Azure não entram aqui: as funções sob teste são puras sobre DataFrames.
"""

from __future__ import annotations

import math
from collections import Counter

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.metricas import (
    COLUNA_CHAVE_MUNICIPAL,
    COLUNA_POPULACAO_2026,
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_MOVIMENTACAO,
    COLUNA_SALDO_POR_10K,
    FATOR_POR_10K,
    saldo_liquido,
    saldo_por_10k,
)

# ---------------------------------------------------------------------------
# Estratégias
# ---------------------------------------------------------------------------

# Chaves de recorte: poucos municípios distintos para forçar agrupamentos reais.
_chaves_municipais = st.sampled_from(["420010", "420020", "420030", "420040"])

# Secao_Industrial (recorte adicional além do município).
_secoes = st.sampled_from(["A", "B", "C"])

# Movimentação: majoritariamente +1/-1 (admissão/desligamento), mas também 0,
# para cobrir o caso de saldo algébrico que se anula.
_movimentacoes = st.sampled_from([1, -1, 0])


@st.composite
def _movimentacoes_com_recorte(draw: st.DrawFn) -> pd.DataFrame:
    """Gera um DataFrame de movimentações com recorte (município × seção).

    Pode ser vazio, para exercitar o caso do conjunto vazio (R4.10).
    """
    n = draw(st.integers(min_value=0, max_value=40))
    chaves = draw(st.lists(_chaves_municipais, min_size=n, max_size=n))
    secoes = draw(st.lists(_secoes, min_size=n, max_size=n))
    movs = draw(st.lists(_movimentacoes, min_size=n, max_size=n))
    return pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: chaves,
            "seção": secoes,
            COLUNA_SALDO_MOVIMENTACAO: movs,
        }
    )


# ---------------------------------------------------------------------------
# Property 13
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 13: Saldo_Liquido é o balanço de admissões e desligamentos
@given(df=_movimentacoes_com_recorte())
@settings(max_examples=100)
def test_prop13_saldo_liquido_e_balanco_de_admissoes_e_desligamentos(
    df: pd.DataFrame,
) -> None:
    """Saldo por recorte = #(+1) − #(−1); conjunto vazio → 0.

    - Para cada recorte presente, o saldo reportado é igual ao número de
      admissões (`+1`) menos o número de desligamentos (`−1`) daquele recorte
      (R4.1).
    - Um recorte cuja soma algébrica se anula aparece com saldo 0; o DataFrame
      vazio não produz nenhum recorte (R4.10).

    Validates: Requirements 4.1, 4.10
    """
    por = [COLUNA_CHAVE_MUNICIPAL, "seção"]
    resultado = saldo_liquido(df, por)

    # Balanço esperado por recorte, calculado de forma independente.
    esperado: dict[tuple[str, str], int] = {}
    for chave, secao, mov in zip(
        df[COLUNA_CHAVE_MUNICIPAL], df["seção"], df[COLUNA_SALDO_MOVIMENTACAO]
    ):
        adm = 1 if mov == 1 else 0
        desl = 1 if mov == -1 else 0
        recorte = (chave, secao)
        esperado[recorte] = esperado.get(recorte, 0) + adm - desl

    if df.empty:
        # Sem registros, nenhum recorte é reportado (R4.10).
        assert resultado.empty
        assert list(resultado.columns) == [*por, COLUNA_SALDO_LIQUIDO]
        return

    # Mesmos recortes nos dois lados (nenhum a mais, nenhum a menos).
    recortes_resultado = {
        (linha[COLUNA_CHAVE_MUNICIPAL], linha["seção"])
        for _, linha in resultado.iterrows()
    }
    assert recortes_resultado == set(esperado)

    # Saldo de cada recorte é o balanço de admissões e desligamentos (R4.1).
    for _, linha in resultado.iterrows():
        recorte = (linha[COLUNA_CHAVE_MUNICIPAL], linha["seção"])
        assert linha[COLUNA_SALDO_LIQUIDO] == esperado[recorte]

    # A soma dos saldos equivale ao total de +1 menos o total de −1 (R4.1).
    contagem = Counter(df[COLUNA_SALDO_MOVIMENTACAO])
    assert resultado[COLUNA_SALDO_LIQUIDO].sum() == contagem[1] - contagem[-1]


# Feature: datathon-caged-sc-pipeline, Property 13: Saldo_Liquido é o balanço de admissões e desligamentos
@given(data=st.data())
@settings(max_examples=100)
def test_prop13_recorte_com_saldo_que_se_anula_e_zero(data: st.DataObject) -> None:
    """Um recorte com igual nº de admissões e desligamentos tem saldo 0 (R4.1).

    Constrói um único recorte com ``k`` admissões e ``k`` desligamentos
    embaralhados; o saldo líquido deve ser exatamente 0.

    Validates: Requirements 4.1, 4.10
    """
    k = data.draw(st.integers(min_value=1, max_value=20))
    movs = [1] * k + [-1] * k
    movs = data.draw(st.permutations(movs))
    df = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["420010"] * len(movs),
            COLUNA_SALDO_MOVIMENTACAO: list(movs),
        }
    )

    resultado = saldo_liquido(df, [COLUNA_CHAVE_MUNICIPAL])

    assert len(resultado) == 1
    assert resultado[COLUNA_SALDO_LIQUIDO].iloc[0] == 0


# Feature: datathon-caged-sc-pipeline, Property 13: Saldo_Liquido é o balanço de admissões e desligamentos
@settings(max_examples=100)
@given(por=st.just([COLUNA_CHAVE_MUNICIPAL]))
def test_prop13_dataframe_vazio_produz_resultado_vazio(por: list[str]) -> None:
    """DataFrame vazio → resultado vazio, sem recortes (R4.10).

    Validates: Requirements 4.1, 4.10
    """
    df = pd.DataFrame(
        {COLUNA_CHAVE_MUNICIPAL: [], COLUNA_SALDO_MOVIMENTACAO: []}
    )
    resultado = saldo_liquido(df, por)
    assert resultado.empty
    assert resultado[COLUNA_SALDO_LIQUIDO].sum() == 0


# ---------------------------------------------------------------------------
# Property 14
# ---------------------------------------------------------------------------

# Saldos líquidos arbitrários (podem ser negativos, zero ou positivos).
_saldos = st.integers(min_value=-5_000, max_value=5_000)

# População maior que zero (fórmula aplicável, R4.2).
_populacao_positiva = st.integers(min_value=1, max_value=2_000_000)

# População ausente ou não positiva (resultado deve ser NaN, R4.3).
_populacao_ausente_ou_zero = st.one_of(
    st.none(),
    st.just(float("nan")),
    st.just(0),
    st.just(0.0),
    st.integers(min_value=-2_000_000, max_value=0),
)


# Feature: datathon-caged-sc-pipeline, Property 14: Saldo_por_10k segue a fórmula ou é ausente
@given(
    saldos=st.lists(_saldos, min_size=1, max_size=20),
    pops=st.lists(
        st.one_of(_populacao_positiva, _populacao_ausente_ou_zero),
        min_size=1,
        max_size=20,
    ),
)
@settings(max_examples=100)
def test_prop14_saldo_por_10k_formula_ou_ausente(
    saldos: list[int], pops: list[object]
) -> None:
    """`(saldo / pop) * 10_000` quando pop > 0; NaN quando ausente ou ≤ 0.

    Cada recorte é um município distinto com seu próprio saldo e população. A
    junção à esquerda preserva todas as linhas de ``saldo_df`` (R4.3).

    Validates: Requirements 4.2, 4.3
    """
    n = min(len(saldos), len(pops))
    saldos = saldos[:n]
    pops = pops[:n]
    chaves = [f"{420000 + i:06d}" for i in range(n)]

    saldo_df = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: chaves,
            COLUNA_SALDO_LIQUIDO: saldos,
        }
    )
    municipios = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: chaves,
            COLUNA_POPULACAO_2026: pops,
        }
    )

    resultado = saldo_por_10k(saldo_df, municipios)

    # Left join preserva todas as linhas e a ordem de saldo_df (R4.3).
    assert len(resultado) == len(saldo_df)
    assert list(resultado[COLUNA_CHAVE_MUNICIPAL]) == chaves

    for saldo, pop, obtido in zip(
        saldos, pops, resultado[COLUNA_SALDO_POR_10K]
    ):
        pop_valida = (
            pop is not None
            and not (isinstance(pop, float) and math.isnan(pop))
            and float(pop) > 0
        )
        if pop_valida:
            esperado = (saldo / float(pop)) * FATOR_POR_10K
            assert obtido == esperado  # R4.2
        else:
            assert math.isnan(obtido)  # R4.3


# Feature: datathon-caged-sc-pipeline, Property 14: Saldo_por_10k segue a fórmula ou é ausente
@given(saldo=_saldos, pop=_populacao_positiva)
@settings(max_examples=100)
def test_prop14_populacao_ausente_na_base_resulta_em_nan(
    saldo: int, pop: int
) -> None:
    """Município sem linha na base (população desconhecida) → NaN (R4.3).

    O recorte existe em ``saldo_df`` mas não há correspondência em
    ``municipios``; o left join deixa a população ausente e o resultado deve
    ser NaN, não a fórmula.

    Validates: Requirements 4.2, 4.3
    """
    saldo_df = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["420010"],
            COLUNA_SALDO_LIQUIDO: [saldo],
        }
    )
    # Base contém outro município, não o do recorte.
    municipios = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["999999"],
            COLUNA_POPULACAO_2026: [pop],
        }
    )

    resultado = saldo_por_10k(saldo_df, municipios)

    assert len(resultado) == 1
    assert math.isnan(resultado[COLUNA_SALDO_POR_10K].iloc[0])
