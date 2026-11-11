"""Testes das figuras do dashboard v2 (`dashboard/figuras.py`).

Funções puras: recebem DataFrames reagregados por `comum.agregar_metricas` e
devolvem `go.Figure`, sem Streamlit nem disco. Cobrem o *empty-state*, a escala
do mapa (neutro no centro, limite por percentil), a cor cinza para amostra
insuficiente, a ordenação das barras (Property 27, adaptada) e a malha.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest
from hypothesis import given
from hypothesis import strategies as st

from dashboard import comum as c
from dashboard import figuras as fig


def _eh_empty_state(figura: go.Figure) -> bool:
    return len(figura.data) == 0 and bool(figura.layout.annotations)


def _geojson_minimo(chaves: list[str]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"chave_municipal": k},
             "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}}
            for k in chaves
        ],
    }


def _metricas_mapa(valores: list[float], movimentos: list[int] | None = None) -> pd.DataFrame:
    n = len(valores)
    mov = movimentos or [500] * n
    return pd.DataFrame({
        c.COLUNA_MUNICIPIO: [f"42{i:04d}" for i in range(n)],
        "rotulo": [f"Município {i}" for i in range(n)],
        c.M_SALDO_10K: valores,
        c.M_MOV: mov,
        c.M_AMOSTRA_OK: [m >= c.MIN_MOVIMENTACOES for m in mov],
    })


def test_mapa_sem_geojson_degrada_para_empty_state():
    assert _eh_empty_state(fig.construir_mapa(_metricas_mapa([1.0]), None, c.M_SALDO_10K))


def test_mapa_usa_dominio_simetrico_para_ancorar_o_neutro_no_zero():
    """Regressão R7.2: com zmin/zmax nos extremos, o neutro sairia do zero."""
    df = _metricas_mapa([-50.0, 20.0, 800.0])
    traco = fig.construir_mapa(df, _geojson_minimo(list(df[c.COLUNA_MUNICIPIO])), c.M_SALDO_10K,
                               rotulo_territorio="rotulo").data[-1]
    assert traco.zmin == -traco.zmax
    assert (0 - traco.zmin) / (traco.zmax - traco.zmin) == 0.5


def test_mapa_limita_a_escala_sem_ultrapassar_o_extremo_observado():
    df = _metricas_mapa([1.0] * 50 + [900.0])
    traco = fig.construir_mapa(df, _geojson_minimo(list(df[c.COLUNA_MUNICIPIO])), c.M_SALDO_10K,
                               rotulo_territorio="rotulo").data[-1]
    assert traco.zmax < 900.0


def test_mapa_pinta_amostra_insuficiente_de_cinza_em_traco_separado():
    df = _metricas_mapa([5.0, 7.0], movimentos=[10, 500])
    figura = fig.construir_mapa(df, _geojson_minimo(list(df[c.COLUNA_MUNICIPIO])), c.M_SALDO_10K,
                                rotulo_territorio="rotulo")
    cinza, colorido = figura.data
    assert list(cinza.locations) == ["420000"] and cinza.showscale is False
    assert list(colorido.locations) == ["420001"]
    assert "n = 10" in cinza.text[0] and "amostra insuficiente" in cinza.text[0]


@st.composite
def _metricas_barras(draw: st.DrawFn) -> pd.DataFrame:
    n = draw(st.integers(min_value=1, max_value=12))
    return pd.DataFrame({
        "categoria": [f"cat{i}" for i in range(n)],
        c.M_SALDO: draw(st.lists(st.floats(-1e5, 1e5, allow_nan=False), min_size=n, max_size=n)),
        c.M_MOV: draw(st.lists(st.integers(0, 10_000), min_size=n, max_size=n)),
    }).assign(**{c.M_AMOSTRA_OK: lambda d: d[c.M_MOV] >= c.MIN_MOVIMENTACOES})


# Feature: datathon-caged-sc-pipeline, Property 27: ranking ordenado de forma não crescente
@given(df=_metricas_barras())
def test_barras_ordenadas_de_forma_nao_crescente(df: pd.DataFrame) -> None:
    figura = fig.construir_barras(df, "categoria", c.M_SALDO, "t")
    valores = list(figura.data[0].x)
    assert valores == sorted(valores, reverse=True)


def test_matriz_e_dispersao_degradam_sem_dados():
    vazio = pd.DataFrame()
    assert _eh_empty_state(fig.construir_matriz(vazio, pd.Series(dtype=str)))
    assert _eh_empty_state(fig.construir_dispersao(vazio, pd.Series(dtype=str), c.M_GAP_SAL, c.M_SAIDA_VOL, "t"))
    assert _eh_empty_state(fig.construir_serie_mensal(vazio))
    assert _eh_empty_state(fig.construir_treemap(vazio))
    assert _eh_empty_state(fig.construir_funil([]))


def test_salario_por_categoria_esconde_categorias_sem_30_salarios():
    medianas = pd.DataFrame({"faixa": ["A", "B"], "mediana_admissao": [2000.0, 3000.0],
                             "mediana_desligamento": [2100.0, 3300.0],
                             "n_admissao": [50, 10], "n_desligamento": [40, 90]})
    figura = fig.construir_salario_por_categoria(medianas, "faixa", "t")
    assert all(list(traco.y) == ["A"] for traco in figura.data)
    assert figura.data[0].text[0] == "R$ 2.000"


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
