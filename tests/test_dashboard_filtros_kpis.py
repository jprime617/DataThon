"""Testes do filtro e dos KPIs do Dashboard (tarefa 12.4).

Valida as duas funções puras de `dashboard/app.py` que alimentam a narrativa do
painel ("localizar → entender → decidir"):

- `aplicar_filtros(df, periodo, regiao, secao, macrofamilia)` — recorta a tabela
  agregada pelas quatro dimensões do painel, em conjunção lógica, com cada filtro
  opcional (R7.5);
- `calcular_kpis(df)` — deriva ≥3 indicadores-chave (rótulo + valor numérico) do
  recorte filtrado, colapsando para zero quando o filtro não casa com nenhum
  registro (R7.1, R7.6).

Cobertura:

- **Property 28 (Hypothesis, ≥100 exemplos)**: para qualquer base agregada e
  qualquer combinação de filtros (período, região, seção, macrofamília), o
  resultado é **correto** (toda linha retornada satisfaz todos os critérios) e
  **completo** (nenhuma linha da base que satisfaz os critérios é omitida).
  Validamos isso comparando o conjunto de índices retornados com o conjunto de
  índices da base que satisfazem a conjunção dos filtros — a diferença simétrica
  deve ser vazia (R7.5).
- **Teste de exemplo dos KPIs**: `calcular_kpis` devolve ao menos 3 pares
  ``(rótulo, valor)`` com rótulo não vazio e valor numérico (R7.1); um filtro que
  não casa com nenhum registro produz um DataFrame vazio cujos KPIs são todos
  ``0.0`` (R7.6).

Todas as funções sob teste são puras: nenhum servidor Streamlit, rede ou disco é
exercido aqui.
"""

from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from dashboard.app import aplicar_filtros, calcular_kpis
from src.agregador import (
    COLUNA_MACROFAMILIA_CBO,
    COLUNA_MES,
    COLUNA_REGIAO,
    COLUNA_SECAO_INDUSTRIAL,
)
from src.metricas import (
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_POR_10K,
    COLUNA_TURNOVER,
)

# ---------------------------------------------------------------------------
# Estratégias Hypothesis
# ---------------------------------------------------------------------------
#
# Domínios pequenos e repetidos em cada dimensão para que combinações se repitam
# na base gerada e para que seleções de filtro frequentemente casem (e às vezes
# não) com os valores presentes — exercitando tanto o caminho "sobra algo" quanto
# "resultado vazio".

_PERIODOS = [202509, 202510, 202511, 202512]
_REGIOES = ["420010", "420020", "420030", "420040"]
_SECOES = ["A", "B", "C", "D"]
_MACROFAMILIAS = ["Indústria", "Serviços", "Logística", "Não classificado"]

_periodo = st.sampled_from(_PERIODOS)
_regiao = st.sampled_from(_REGIOES)
_secao = st.sampled_from(_SECOES)
_macro = st.sampled_from(_MACROFAMILIAS)
_valor = st.floats(
    min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False
)


@st.composite
def _base_agregada(draw: st.DrawFn) -> pd.DataFrame:
    """Gera uma tabela agregada com as 4 dimensões de filtro e métricas.

    Cada linha é um recorte ``(mes, regiao, secao_industrial, macrofamilia_cbo)``
    com métricas numéricas associadas. Linhas podem repetir combinações de
    dimensões — fiel ao que o painel recebe após filtros parciais.
    """
    n = draw(st.integers(min_value=0, max_value=40))
    linhas = draw(
        st.lists(
            st.tuples(_periodo, _regiao, _secao, _macro, _valor, _valor, _valor),
            min_size=n,
            max_size=n,
        )
    )
    return pd.DataFrame(
        linhas,
        columns=[
            COLUNA_MES,
            COLUNA_REGIAO,
            COLUNA_SECAO_INDUSTRIAL,
            COLUNA_MACROFAMILIA_CBO,
            COLUNA_SALDO_LIQUIDO,
            COLUNA_SALDO_POR_10K,
            COLUNA_TURNOVER,
        ],
    )


# Uma seleção de filtro é, para cada dimensão, independentemente:
#   - None  → sem restrição;
#   - escalar → igualdade;
#   - lista → pertença ao conjunto (possivelmente com valores fora da base).
def _selecao(valores: st.SearchStrategy):
    return st.one_of(
        st.none(),
        valores,
        st.lists(valores, min_size=0, max_size=3),
    )


# ---------------------------------------------------------------------------
# Property 28 — filtro correto e completo (R7.5)
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 28: Filtro do dashboard é correto
# e completo — para qualquer base agregada e combinação de filtros (período,
# região, seção, macrofamília), todo registro no resultado satisfaz todos os
# critérios do filtro e nenhum registro que satisfaz os critérios é omitido.
@settings(max_examples=100)
@given(
    df=_base_agregada(),
    periodo=_selecao(_periodo),
    regiao=_selecao(_regiao),
    secao=_selecao(_secao),
    macrofamilia=_selecao(_macro),
)
def test_prop28_filtro_correto_e_completo(
    df: pd.DataFrame, periodo, regiao, secao, macrofamilia
) -> None:
    """Property 28: `aplicar_filtros` é correto (sem intrusos) e completo (sem omissões).

    Oráculo independente: para cada dimensão, computamos o conjunto de valores
    aceitos (``None``/vazio = aceita tudo; escalar = {valor}; lista = conjunto) e
    marcamos as linhas da base que satisfazem **todas** as dimensões. O conjunto
    de índices esperado deve ser idêntico ao conjunto de índices retornado por
    `aplicar_filtros`:

    - **correto**: nenhum índice retornado está fora do esperado (sem intrusos);
    - **completo**: nenhum índice esperado foi omitido do resultado.

    Também verificamos que o filtro não altera a base original nem o schema.

    Validates: Requirements 7.5
    """
    df_original = df.copy()
    resultado = aplicar_filtros(df, periodo, regiao, secao, macrofamilia)

    # Schema preservado e base não mutada.
    assert list(resultado.columns) == list(df.columns)
    pd.testing.assert_frame_equal(df, df_original)

    # Oráculo: conjunto esperado de índices via conjunção das 4 dimensões.
    def _aceita(selecao, valor) -> bool:
        if selecao is None:
            return True
        if isinstance(selecao, list):
            if not selecao:  # lista vazia = sem restrição (R7.5)
                return True
            return valor in selecao
        return valor == selecao

    esperados = {
        idx
        for idx, linha in df.iterrows()
        if _aceita(periodo, linha[COLUNA_MES])
        and _aceita(regiao, linha[COLUNA_REGIAO])
        and _aceita(secao, linha[COLUNA_SECAO_INDUSTRIAL])
        and _aceita(macrofamilia, linha[COLUNA_MACROFAMILIA_CBO])
    }
    obtidos = set(resultado.index)

    # Correto + completo: os conjuntos coincidem exatamente.
    assert obtidos == esperados

    # Reforço de "correto": cada linha retornada satisfaz os quatro critérios.
    for _, linha in resultado.iterrows():
        assert _aceita(periodo, linha[COLUNA_MES])
        assert _aceita(regiao, linha[COLUNA_REGIAO])
        assert _aceita(secao, linha[COLUNA_SECAO_INDUSTRIAL])
        assert _aceita(macrofamilia, linha[COLUNA_MACROFAMILIA_CBO])


# ---------------------------------------------------------------------------
# Exemplo — KPIs renderizados e zeragem em filtro vazio (R7.1, R7.6)
# ---------------------------------------------------------------------------


def _agregado_exemplo() -> pd.DataFrame:
    """Tabela agregada mínima com as colunas que os KPIs consomem."""
    return pd.DataFrame(
        {
            COLUNA_MES: [202509, 202509, 202510],
            COLUNA_REGIAO: ["420010", "420020", "420010"],
            COLUNA_SECAO_INDUSTRIAL: ["C", "C", "A"],
            COLUNA_MACROFAMILIA_CBO: ["Indústria", "Serviços", "Indústria"],
            COLUNA_SALDO_LIQUIDO: [10.0, -4.0, 6.0],
            COLUNA_SALDO_POR_10K: [2.5, -1.0, 1.5],
            COLUNA_TURNOVER: [0.3, 0.1, 0.5],
        }
    )


def test_calcular_kpis_retorna_ao_menos_tres_pares_rotulo_valor() -> None:
    """`calcular_kpis` devolve ≥3 pares (rótulo, valor numérico) (R7.1).

    Cada KPI tem rótulo legível não vazio e valor numérico finito, satisfazendo o
    contrato "no mínimo 3 KPIs, cada um exibindo rótulo e valor numérico".

    Requirements: 7.1
    """
    kpis = calcular_kpis(_agregado_exemplo())

    assert len(kpis) >= 3
    rotulos = set()
    for rotulo, valor in kpis:
        assert isinstance(rotulo, str) and rotulo.strip()
        assert isinstance(valor, float)
        assert math.isfinite(valor)
        rotulos.add(rotulo)
    # Rótulos distintos — KPIs não se repetem.
    assert len(rotulos) == len(kpis)

    # Sanidade dos valores: saldo líquido total = soma da coluna.
    valores = dict(kpis)
    from dashboard.app import KPI_SALDO_LIQUIDO_TOTAL

    assert valores[KPI_SALDO_LIQUIDO_TOTAL] == 12.0  # 10 - 4 + 6


def test_filtro_sem_registros_zera_todos_os_kpis() -> None:
    """Filtro que não casa com nenhum registro → DataFrame vazio e KPIs em zero (R7.6).

    Selecionamos uma região inexistente na base: `aplicar_filtros` devolve um
    recorte vazio e `calcular_kpis` colapsa **todos** os KPIs para ``0.0``, sem
    levantar exceção, mantendo ao menos 3 indicadores.

    Requirements: 7.1, 7.6
    """
    df = _agregado_exemplo()

    vazio = aplicar_filtros(df, regiao="999999")
    assert vazio.empty
    assert list(vazio.columns) == list(df.columns)

    kpis = calcular_kpis(vazio)
    assert len(kpis) >= 3
    for rotulo, valor in kpis:
        assert isinstance(rotulo, str) and rotulo.strip()
        assert valor == 0.0
