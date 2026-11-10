"""Testes das visualizações do Dashboard (tarefa 12.6 — R7.2, R7.3, R7.4).

Exercitam as funções puras construtoras de figuras de `dashboard/app.py`
(`construir_ranking`, `construir_mapa`, `construir_dispersao`), que recebem um
DataFrame (e, no mapa, o GeoJSON) e retornam um `plotly.graph_objects.Figure`
sem importar Streamlit nem tocar em disco/rede. Assim a lógica das visualizações
é validada sem um servidor Streamlit e sem artefatos externos.

Cobertura:

- **Property 27** (property-based, Hypothesis): o ranking de Secao_Industrial é
  ordenado de forma **não crescente** por `saldo_liquido` (R7.3). A ordenação é
  verificada inspecionando os dados do trace de barras da figura retornada.
- **Testes de exemplo**: `construir_mapa` (com um GeoJSON mínimo), `construir_ranking`
  e `construir_dispersao` retornam uma figura Plotly válida com dados mínimos
  (R7.2, R7.4), e degradam graciosamente para o *empty-state* quando as colunas
  necessárias/o GeoJSON estão ausentes (R7.6).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from hypothesis import given
from hypothesis import strategies as st

from dashboard.app import (
    COLUNA_GRAU_INSTRUCAO,
    COLUNA_SALARIO_MEDIO_ADMISSAO,
    construir_dispersao,
    construir_mapa,
    construir_ranking,
)
from src.agregador import (
    COLUNA_MACROFAMILIA_CBO,
    COLUNA_MUNICIPIO,
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_POR_10K,
    COLUNA_SECAO_INDUSTRIAL,
    COLUNA_TURNOVER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Seções CNAE industriais do foco do desafio (B, C, D, E, F) — rótulos usados
# como categorias do ranking.
_SECOES = ["B", "C", "D", "E", "F"]


def _eh_empty_state(figura: go.Figure) -> bool:
    """True se a figura é o *empty-state* (sem traces, com anotação central)."""
    return len(figura.data) == 0 and bool(figura.layout.annotations)


# ---------------------------------------------------------------------------
# Property 27: Ranking de setores é ordenado de forma não crescente (R7.3)
# ---------------------------------------------------------------------------


@st.composite
def _agregado_ranking(draw: st.DrawFn) -> pd.DataFrame:
    """Gera uma tabela agregada mínima para o ranking de seções.

    Sorteia um subconjunto não vazio de seções e, para cada seção, de 1 a 4
    linhas com `saldo_liquido` (pode ser negativo) e `turnover` em [0, 1]. Várias
    linhas por seção exercitam a agregação (soma de saldo, média de turnover)
    antes da ordenação, que é o alvo da propriedade.
    """
    secoes = draw(
        st.lists(st.sampled_from(_SECOES), min_size=1, max_size=5, unique=True)
    )
    linhas: list[dict[str, object]] = []
    for secao in secoes:
        n = draw(st.integers(min_value=1, max_value=4))
        for _ in range(n):
            linhas.append(
                {
                    COLUNA_SECAO_INDUSTRIAL: secao,
                    COLUNA_SALDO_LIQUIDO: draw(
                        st.floats(
                            min_value=-1e6,
                            max_value=1e6,
                            allow_nan=False,
                            allow_infinity=False,
                        )
                    ),
                    COLUNA_TURNOVER: draw(
                        st.floats(
                            min_value=0.0,
                            max_value=1.0,
                            allow_nan=False,
                            allow_infinity=False,
                        )
                    ),
                }
            )
    return pd.DataFrame(linhas)


# Feature: datathon-caged-sc-pipeline, Property 27: Ranking de setores é ordenado de forma não crescente
@given(df=_agregado_ranking())
def test_ranking_ordenado_nao_crescente(df: pd.DataFrame) -> None:
    """O ranking expõe os saldos das seções em ordem não crescente (R7.3).

    Inspeciona o trace de barras da figura: o eixo que carrega `saldo_liquido`
    (x, pois as barras são horizontais) deve estar ordenado de forma não
    crescente, refletindo o ranking decrescente por saldo líquido exigido por
    R7.3.
    """
    figura = construir_ranking(df)

    # Com ao menos uma seção, há dados: deve ser um gráfico de barras, não o
    # empty-state.
    assert len(figura.data) == 1
    barra = figura.data[0]
    assert isinstance(barra, go.Bar)

    saldos = list(barra.x)
    # Propriedade central: saldos em ordem não crescente (decrescente ou igual).
    assert all(
        anterior >= proximo
        for anterior, proximo in zip(saldos, saldos[1:])
    ), f"saldos do ranking não estão em ordem não crescente: {saldos}"

    # Cada seção distinta aparece exatamente uma vez (agregação por seção).
    assert len(saldos) == df[COLUNA_SECAO_INDUSTRIAL].nunique()


# ---------------------------------------------------------------------------
# Testes de exemplo das visualizações (R7.2, R7.3, R7.4, R7.6)
# ---------------------------------------------------------------------------


def _geojson_minimo() -> dict:
    """GeoJSON mínimo com duas features de municípios de SC (chave de 6 dígitos)."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"chave_municipal": "420010"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"chave_municipal": "420020"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[1, 1], [1, 2], [2, 2], [2, 1], [1, 1]]],
                },
            },
        ],
    }


def test_construir_mapa_com_dados_minimos_retorna_figura() -> None:
    """O mapa coroplético renderiza com dados e GeoJSON mínimos (R7.2)."""
    df = pd.DataFrame(
        {
            COLUNA_MUNICIPIO: ["420010", "420020"],
            COLUNA_SALDO_POR_10K: [-5.0, 8.0],
        }
    )

    figura = construir_mapa(df, _geojson_minimo())

    assert isinstance(figura, go.Figure)
    assert len(figura.data) == 1
    trace = figura.data[0]
    assert isinstance(trace, go.Choropleth)
    # Um valor por município (dois municípios distintos no recorte).
    assert set(trace.locations) == {"420010", "420020"}
    # Escala divergente ancorada no zero, com legenda de mín/máx (R7.2).
    assert trace.zmid == 0
    assert trace.zmin == -5.0
    assert trace.zmax == 8.0


def test_construir_mapa_sem_geojson_degrada_para_empty_state() -> None:
    """Sem a malha (GeoJSON None), o mapa cai no empty-state sem quebrar (R7.6)."""
    df = pd.DataFrame(
        {COLUNA_MUNICIPIO: ["420010"], COLUNA_SALDO_POR_10K: [1.0]}
    )

    figura = construir_mapa(df, None)

    assert isinstance(figura, go.Figure)
    assert _eh_empty_state(figura)


def test_construir_ranking_com_dados_minimos_retorna_figura_ordenada() -> None:
    """O ranking renderiza barras ordenadas decrescentemente por saldo (R7.3)."""
    df = pd.DataFrame(
        {
            COLUNA_SECAO_INDUSTRIAL: ["C", "F", "D"],
            COLUNA_SALDO_LIQUIDO: [10.0, 30.0, 20.0],
            COLUNA_TURNOVER: [0.2, 0.5, 0.3],
        }
    )

    figura = construir_ranking(df)

    assert isinstance(figura, go.Figure)
    assert len(figura.data) == 1
    barra = figura.data[0]
    assert isinstance(barra, go.Bar)
    # Ordem decrescente por saldo: F (30) > D (20) > C (10).
    assert list(barra.x) == [30.0, 20.0, 10.0]
    assert list(barra.y) == ["F", "D", "C"]
    # O turnover médio da seção acompanha cada barra (customdata — R7.3).
    assert list(barra.customdata) == [0.5, 0.3, 0.2]


def test_construir_ranking_sem_colunas_degrada_para_empty_state() -> None:
    """Faltando colunas necessárias, o ranking cai no empty-state (R7.6)."""
    df = pd.DataFrame({COLUNA_SECAO_INDUSTRIAL: ["C"]})

    figura = construir_ranking(df)

    assert isinstance(figura, go.Figure)
    assert _eh_empty_state(figura)


def test_construir_dispersao_com_dados_minimos_retorna_figura() -> None:
    """A dispersão renda × escolaridade renderiza segmentada por setor (R7.4)."""
    df = pd.DataFrame(
        {
            COLUNA_SALARIO_MEDIO_ADMISSAO: [2000.0, 3500.0, 2800.0],
            COLUNA_GRAU_INSTRUCAO: [
                "Médio Completo",
                "Superior Completo",
                "Médio Completo",
            ],
            COLUNA_MACROFAMILIA_CBO: [
                "Operacional de Produção",
                "Engenharia/Técnico",
                "Operacional de Produção",
            ],
        }
    )

    figura = construir_dispersao(df)

    assert isinstance(figura, go.Figure)
    # Um trace de pontos por macrofamília distinta (2 segmentos).
    assert len(figura.data) == 2
    assert all(isinstance(trace, go.Scatter) for trace in figura.data)
    nomes_segmentos = {trace.name for trace in figura.data}
    assert nomes_segmentos == {
        "Operacional de Produção",
        "Engenharia/Técnico",
    }


def test_construir_dispersao_sem_colunas_degrada_para_empty_state() -> None:
    """Sem as colunas de salário/escolaridade, a dispersão cai no empty-state (R7.6)."""
    df = pd.DataFrame({COLUNA_SECAO_INDUSTRIAL: ["C"], COLUNA_SALDO_LIQUIDO: [1.0]})

    figura = construir_dispersao(df)

    assert isinstance(figura, go.Figure)
    assert _eh_empty_state(figura)
