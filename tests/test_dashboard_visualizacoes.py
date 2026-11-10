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

import json
from pathlib import Path

import pandas as pd
import pytest
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


def _geojson_minimo(chaves: list[str] | None = None) -> dict:
    """GeoJSON mínimo com uma feature quadrada por chave municipal.

    Os anéis são escritos no sentido **horário**, a convenção do d3-geo que o
    Plotly usa para desenhar o coroplético — a mesma que
    `scripts/baixar_malha_sc.py` aplica à malha real.
    """
    chaves = chaves if chaves is not None else ["420010", "420020"]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"chave_municipal": chave},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[i, 0], [i, 1], [i + 1, 1], [i + 1, 0], [i, 0]]
                    ],
                },
            }
            for i, chave in enumerate(chaves)
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
    # Escala divergente ancorada no zero: domínio simétrico (R7.2). O limite
    # vem de um percentil de |valor|, então nunca ultrapassa o extremo observado.
    assert trace.zmin == -trace.zmax
    assert 0 < trace.zmax <= 8.0
    # A legenda expõe os extremos reais, mesmo quando a escala satura.
    rotulos = " ".join(trace.colorbar.ticktext)
    assert "-5" in rotulos and "8" in rotulos


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


# ---------------------------------------------------------------------------
# Escala do mapa: branco no zero (R7.2)
# ---------------------------------------------------------------------------


def test_mapa_usa_dominio_simetrico_para_ancorar_o_branco_no_zero():
    """O domínio da escala é simétrico, então o neutro cai no saldo nulo (R7.2).

    Regressão: com `zmin`/`zmax` nos extremos observados, o branco da escala
    divergente cai no **meio do intervalo**, não no zero. Num recorte cujo
    máximo é muito maior que o módulo do mínimo, municípios com saldo positivo
    acabam pintados do lado negativo da escala — o oposto do que R7.2 pede.
    """
    df = pd.DataFrame(
        {
            COLUNA_MUNICIPIO: ["420005", "420010", "420020"],
            COLUNA_SALDO_POR_10K: [-50.0, 20.0, 800.0],
        }
    )
    figura = construir_mapa(df, _geojson_minimo(["420005", "420010", "420020"]))
    traco = figura.data[0]

    assert traco.zmin == -traco.zmax, "o domínio da escala precisa ser simétrico"
    assert traco.zmin < 0 < traco.zmax
    # O zero está exatamente no meio do domínio — onde a escala tem o branco.
    assert (0 - traco.zmin) / (traco.zmax - traco.zmin) == 0.5


def test_mapa_limita_a_escala_sem_ultrapassar_o_extremo_observado():
    """Um extremo isolado não define sozinho o domínio, mas o limite não o excede."""
    valores = [1.0] * 50 + [900.0]
    df = pd.DataFrame(
        {
            COLUNA_MUNICIPIO: [f"4200{i:02d}" for i in range(len(valores))],
            COLUNA_SALDO_POR_10K: valores,
        }
    )
    figura = construir_mapa(
        df, _geojson_minimo([f"4200{i:02d}" for i in range(len(valores))])
    )
    traco = figura.data[0]

    assert traco.zmax <= 900.0, "o limite não pode ultrapassar o máximo observado"
    assert traco.zmax < 900.0, "um único extremo não deveria definir a escala"


# ---------------------------------------------------------------------------
# Malha de municípios: orientação dos anéis (R7.2)
# ---------------------------------------------------------------------------

_MALHA = Path(__file__).resolve().parent.parent / "dashboard" / "geo" / "sc_municipios.geojson"


def _area_assinada(anel: list) -> float:
    """Área assinada pela fórmula do cadarço: positiva = anti-horário."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(anel, anel[1:])) / 2


def _aneis_externos(geometria: dict):
    if geometria["type"] == "Polygon":
        yield geometria["coordinates"][0]
    elif geometria["type"] == "MultiPolygon":
        for poligono in geometria["coordinates"]:
            yield poligono[0]


@pytest.mark.skipif(not _MALHA.is_file(), reason="malha de municípios ausente")
def test_malha_tem_aneis_externos_no_sentido_horario():
    """Os anéis externos são horários — a convenção do d3-geo, que o Plotly usa.

    Regressão de um defeito mudo: o RFC 7946 manda o anel externo ser
    anti-horário e é assim que o IBGE entrega, mas o `d3-geo` usa a convenção
    **oposta** e lê um anel anti-horário como *todo o globo menos aquela área*.
    O mapa então vira um retângulo de cor única com os municípios como buracos —
    renderiza sem erro nenhum, o que é exatamente o que torna o defeito difícil
    de notar. `scripts/baixar_malha_sc.py` rebobina os anéis ao gerar o arquivo.
    """
    malha = json.loads(_MALHA.read_text(encoding="utf-8"))
    anti_horarios = [
        feature["properties"].get("chave_municipal")
        for feature in malha["features"]
        for anel in _aneis_externos(feature["geometry"])
        if _area_assinada(anel) > 0
    ]
    assert not anti_horarios, (
        f"{len(anti_horarios)} anel(éis) externo(s) anti-horário(s) "
        f"(ex.: {anti_horarios[:5]}) — rode `python scripts/baixar_malha_sc.py`"
    )


@pytest.mark.skipif(not _MALHA.is_file(), reason="malha de municípios ausente")
def test_malha_cobre_os_295_municipios_com_chave_de_6_digitos():
    """Toda feature expõe a `chave_municipal` de 6 dígitos usada pelo agregado."""
    malha = json.loads(_MALHA.read_text(encoding="utf-8"))
    chaves = [f["properties"].get("chave_municipal") for f in malha["features"]]
    assert len(chaves) == 295, f"esperado 295 municípios de SC, veio {len(chaves)}"
    assert all(c and len(c) == 6 and c.isdecimal() for c in chaves)
    assert len(set(chaves)) == 295, "há chaves municipais duplicadas na malha"
