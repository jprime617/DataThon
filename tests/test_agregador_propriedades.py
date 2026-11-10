"""Testes de propriedade do Agregador (tarefa 10.2).

Valida, com Hypothesis (mín. 100 exemplos), a função `agregar(df_metricas,
municipios)` de `src/agregador.py`, que consolida a base enriquecida em uma
tabela agregada pequena com uma linha por recorte e os indicadores municipais
anexados (R6):

- Property 23: Integridade do agregado (unicidade e origem) — para qualquer
  base de entrada, cada combinação `(regiao/municipio, secao_industrial,
  macrofamilia_cbo, mes)` aparece no máximo uma vez, e toda linha do agregado
  corresponde a pelo menos um registro de origem; combinações sem registros são
  omitidas (R6.1, R6.2).
- Property 25: Métricas do agregado têm no máximo 2 casas decimais — cada
  métrica numérica (`saldo_liquido`, `saldo_por_10k`, `turnover`,
  `indice_aquecimento`) é NaN ou igual ao próprio valor arredondado a 2 casas
  (R6.5).
- Property 26: Indicadores municipais anexados correspondem à base — para
  qualquer recorte municipal, população 2026, IDHM 2010 e PIB per capita 2023
  anexados são iguais aos da Base_de_Municipios daquele município, ou NaN
  quando o município não possui o indicador (R6.6, R6.7).

As funções sob teste são puras sobre DataFrames; LLM e Azure não entram aqui.
"""

from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agregador import (
    COLUNA_IDHM_2010,
    COLUNA_MACROFAMILIA_CBO,
    COLUNA_MES,
    COLUNA_MUNICIPIO,
    COLUNA_PIB_PER_CAPITA_2023,
    COLUNA_POPULACAO_2026,
    COLUNA_REGIAO,
    COLUNA_SECAO_INDUSTRIAL,
    ORIGEM_IDHM_2010,
    ORIGEM_PIB_PER_CAPITA_2023,
    ORIGEM_POPULACAO_2026,
    agregar,
)
from src.cbo_ia import COLUNA_MACROFAMILIA
from src.metricas import (
    COLUNA_CHAVE_MUNICIPAL,
    COLUNA_COMPETENCIA,
    COLUNA_INDICE_AQUECIMENTO,
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_MOVIMENTACAO,
    COLUNA_SALDO_POR_10K,
    COLUNA_SECAO,
    COLUNA_ESTOQUE_BASE,
    COLUNA_TURNOVER,
)

# ---------------------------------------------------------------------------
# Estratégias
# ---------------------------------------------------------------------------

# Poucos municípios/seções/macrofamílias/meses distintos para forçar que
# combinações se repitam na entrada e, assim, exercitar a agregação real.
_chaves_municipais = st.sampled_from(["420010", "420020", "420030", "420040"])
_secoes = st.sampled_from(["A", "B", "C"])
_macrofamilias = st.sampled_from(["Indústria", "Serviços", "Não classificado"])
_meses = st.sampled_from([202509, 202510, 202511, 202512])

# Movimentação: majoritariamente +1/-1 (admissão/desligamento).
_movimentacoes = st.sampled_from([1, -1])

# Estoque base (tamestabjan): positivo para que o turnover seja calculável.
_estoques = st.integers(min_value=1, max_value=500)

# Métricas das colunas numéricas do agregado (R6.5).
_COLUNAS_METRICAS = [
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_POR_10K,
    COLUNA_TURNOVER,
    COLUNA_INDICE_AQUECIMENTO,
]

# Colunas de recorte do agregado na saída.
_COLUNAS_RECORTE_SAIDA = [
    COLUNA_REGIAO,
    COLUNA_SECAO_INDUSTRIAL,
    COLUNA_MACROFAMILIA_CBO,
    COLUNA_MES,
]


@st.composite
def _base_enriquecida(draw: st.DrawFn) -> pd.DataFrame:
    """Gera uma base enriquecida (CAGED cruzado + macrofamília).

    Produz um DataFrame com as colunas de recorte (`chave_municipal`, `seção`,
    `macrofamilia`, `competênciamov`) e as colunas necessárias às métricas
    (`saldomovimentação`, `tamestabjan`). Pode ser vazia, para exercitar o
    caso do DataFrame vazio (R6.2).
    """
    n = draw(st.integers(min_value=0, max_value=40))
    chaves = draw(st.lists(_chaves_municipais, min_size=n, max_size=n))
    secoes = draw(st.lists(_secoes, min_size=n, max_size=n))
    macros = draw(st.lists(_macrofamilias, min_size=n, max_size=n))
    meses = draw(st.lists(_meses, min_size=n, max_size=n))
    movs = draw(st.lists(_movimentacoes, min_size=n, max_size=n))
    estoques = draw(st.lists(_estoques, min_size=n, max_size=n))
    return pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: chaves,
            COLUNA_SECAO: secoes,
            COLUNA_MACROFAMILIA: macros,
            COLUNA_COMPETENCIA: meses,
            COLUNA_SALDO_MOVIMENTACAO: movs,
            COLUNA_ESTOQUE_BASE: estoques,
        }
    )


# População, IDHM e PIB per capita possivelmente ausentes (NaN) por indicador.
_populacao = st.one_of(
    st.integers(min_value=1, max_value=2_000_000),
    st.none(),
)
_idhm = st.one_of(
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    st.none(),
)
_pib = st.one_of(
    st.floats(min_value=0.0, max_value=500_000.0, allow_nan=False, allow_infinity=False),
    st.none(),
)


@st.composite
def _municipios(draw: st.DrawFn) -> pd.DataFrame:
    """Gera uma Base_de_Municipios com chave_municipal + indicadores.

    Cada município conhecido tem, independentemente, cada indicador presente
    (um número) ou ausente (NaN), para exercitar o preenchimento com NaN (R6.7).
    Alguns municípios de recorte podem não aparecer na base (também → NaN).
    """
    municipios = draw(
        st.lists(
            st.sampled_from(["420010", "420020", "420030", "420040"]),
            min_size=0,
            max_size=4,
            unique=True,
        )
    )
    pops = [draw(_populacao) for _ in municipios]
    idhms = [draw(_idhm) for _ in municipios]
    pibs = [draw(_pib) for _ in municipios]
    return pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: municipios,
            ORIGEM_POPULACAO_2026: pops,
            ORIGEM_IDHM_2010: idhms,
            ORIGEM_PIB_PER_CAPITA_2023: pibs,
        }
    )


def _combinacoes_entrada(df: pd.DataFrame) -> set[tuple[object, object, object, object]]:
    """Combinações distintas de recorte presentes na base de entrada."""
    return {
        (chave, secao, macro, mes)
        for chave, secao, macro, mes in zip(
            df[COLUNA_CHAVE_MUNICIPAL],
            df[COLUNA_SECAO],
            df[COLUNA_MACROFAMILIA],
            df[COLUNA_COMPETENCIA],
        )
    }


# ---------------------------------------------------------------------------
# Property 23: Integridade do agregado (unicidade e origem)
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 23: Integridade do agregado (unicidade e origem)
@given(df=_base_enriquecida(), municipios=_municipios())
@settings(max_examples=100)
def test_prop23_integridade_do_agregado_unicidade_e_origem(
    df: pd.DataFrame, municipios: pd.DataFrame
) -> None:
    """Cada recorte aparece no máximo uma vez e vem de ao menos um registro.

    - Unicidade: cada combinação `(municipio, secao_industrial,
      macrofamilia_cbo, mes)` aparece no máximo uma vez no agregado (R6.1).
      O recorte geográfico é o **município** — `regiao` (a mesorregião do IBGE)
      é um atributo descritivo do município, constante dentro dele, e portanto
      não entra na chave: várias chaves municipais compartilham a mesma região.
    - Origem: toda linha do agregado corresponde a uma combinação presente na
      base de entrada; combinações sem registros são omitidas (R6.2).

    Validates: Requirements 6.1, 6.2
    """
    resultado = agregar(df, municipios)

    if df.empty:
        # Sem registros, nenhum recorte a reportar (R6.2).
        assert resultado.empty
        return

    chaves_saida = [
        (
            linha[COLUNA_MUNICIPIO],
            linha[COLUNA_SECAO_INDUSTRIAL],
            linha[COLUNA_MACROFAMILIA_CBO],
            linha[COLUNA_MES],
        )
        for _, linha in resultado.iterrows()
    ]

    # Unicidade: nenhuma combinação se repete no agregado (R6.1).
    assert len(chaves_saida) == len(set(chaves_saida))

    # Origem: o conjunto de recortes do agregado é exatamente o conjunto
    # distinto de recortes presentes na entrada (nenhum espúrio, nenhum omitido
    # indevidamente) — R6.1/R6.2. O município == chave_municipal.
    esperado = _combinacoes_entrada(df)
    assert set(chaves_saida) == esperado

    # Consistência do schema: a região é função do município — cada município
    # tem exatamente uma região em todas as linhas em que aparece.
    por_municipio = resultado.groupby(COLUNA_MUNICIPIO)[COLUNA_REGIAO].nunique()
    assert (por_municipio == 1).all()


# ---------------------------------------------------------------------------
# Property 25: Métricas do agregado têm no máximo 2 casas decimais
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 25: Métricas do agregado têm no máximo 2 casas decimais
@given(df=_base_enriquecida(), municipios=_municipios())
@settings(max_examples=100)
def test_prop25_metricas_tem_no_maximo_duas_casas_decimais(
    df: pd.DataFrame, municipios: pd.DataFrame
) -> None:
    """Cada métrica numérica é NaN ou igual ao próprio valor com 2 casas.

    Para toda linha do agregado e cada métrica (`saldo_liquido`, `saldo_por_10k`,
    `turnover`, `indice_aquecimento`), o valor é ausente (NaN) ou idêntico ao seu
    arredondamento a 2 casas decimais (R6.5).

    Validates: Requirements 6.5
    """
    resultado = agregar(df, municipios)

    for coluna in _COLUNAS_METRICAS:
        assert coluna in resultado.columns
        for valor in resultado[coluna]:
            numero = float(valor)
            if math.isnan(numero):
                continue
            assert numero == round(numero, 2)


# ---------------------------------------------------------------------------
# Property 26: Indicadores municipais anexados correspondem à base
# ---------------------------------------------------------------------------


def _indicador_esperado(municipios: pd.DataFrame, chave: object, origem: str) -> float:
    """Valor numérico esperado do indicador `origem` para `chave`, ou NaN.

    Reproduz, de forma independente da implementação, o indicador que a base
    atribui ao município: o valor da (única) linha do município coagido para
    float, ou NaN quando o município não está na base ou o valor é ausente.
    """
    linhas = municipios[municipios[COLUNA_CHAVE_MUNICIPAL] == chave]
    if linhas.empty:
        return math.nan
    valor = linhas[origem].iloc[0]
    numero = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    return float(numero)


# Feature: datathon-caged-sc-pipeline, Property 26: Indicadores municipais anexados correspondem à base
@given(df=_base_enriquecida(), municipios=_municipios())
@settings(max_examples=100)
def test_prop26_indicadores_anexados_correspondem_a_base(
    df: pd.DataFrame, municipios: pd.DataFrame
) -> None:
    """Indicadores anexados são os da base para o município, ou NaN se ausentes.

    Para cada recorte do agregado, população 2026, IDHM 2010 e PIB per capita
    2023 anexados devem ser iguais aos da Base_de_Municipios para aquele
    município (identificado pela chave em `regiao`/`municipio`), ou NaN quando o
    município não está na base ou não possui o indicador (R6.6, R6.7).

    Validates: Requirements 6.6, 6.7
    """
    resultado = agregar(df, municipios)

    if df.empty:
        assert resultado.empty
        return

    indicadores = [
        (COLUNA_POPULACAO_2026, ORIGEM_POPULACAO_2026),
        (COLUNA_IDHM_2010, ORIGEM_IDHM_2010),
        (COLUNA_PIB_PER_CAPITA_2023, ORIGEM_PIB_PER_CAPITA_2023),
    ]

    for coluna_saida, _ in indicadores:
        assert coluna_saida in resultado.columns

    for _, linha in resultado.iterrows():
        chave = linha[COLUNA_MUNICIPIO]
        for coluna_saida, origem in indicadores:
            obtido = float(linha[coluna_saida])
            esperado = _indicador_esperado(municipios, chave, origem)
            if math.isnan(esperado):
                assert math.isnan(obtido)
            else:
                assert obtido == esperado


# Feature: datathon-caged-sc-pipeline, Property 26: Indicadores municipais anexados correspondem à base
@given(df=_base_enriquecida())
@settings(max_examples=100)
def test_prop26_municipio_ausente_da_base_resulta_em_nan(df: pd.DataFrame) -> None:
    """Município sem linha na base → indicadores NaN (R6.7).

    A Base_de_Municipios só contém um município que não aparece em nenhum
    recorte; portanto todos os indicadores anexados devem ser NaN.

    Validates: Requirements 6.6, 6.7
    """
    municipios = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["999999"],
            ORIGEM_POPULACAO_2026: [1234],
            ORIGEM_IDHM_2010: [0.75],
            ORIGEM_PIB_PER_CAPITA_2023: [42000.0],
        }
    )

    resultado = agregar(df, municipios)

    if df.empty:
        assert resultado.empty
        return

    for coluna in (COLUNA_POPULACAO_2026, COLUNA_IDHM_2010, COLUNA_PIB_PER_CAPITA_2023):
        assert resultado[coluna].isna().all()
