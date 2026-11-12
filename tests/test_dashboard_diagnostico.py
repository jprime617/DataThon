"""M3.C1: o "por quê" de cada cartão de alerta, numa frase sem jargão."""

import pandas as pd

from dashboard import comum as c
from dashboard.paginas.diagnostico import frase_porque


def _u(saida: float, gap: float) -> pd.Series:
    return pd.Series({c.M_SAIDA_VOL: saida, c.M_GAP_SAL: gap})


def test_frase_prioriza_a_causa_salarial():
    assert frase_porque(_u(0.6, 0.87), [c.CAUSA_SALARIAL], 0.47).startswith("Quem entra ganha 87%")


def test_frase_de_retencao_compara_com_o_estado():
    frase = frase_porque(_u(0.6, 1.02), [c.CAUSA_RETENCAO], 0.47)
    assert "60%" in frase and "estado: 47%" in frase and "reter" in frase


def test_frase_sem_causa_nao_inventa_explicacao():
    assert "nenhuma causa isolada" in frase_porque(_u(0.5, 0.97), [], 0.47)


def test_matriz_legivel_so_cor_e_eixos_em_palavras():
    """M3.C2: sem os 4 símbolos e sem z-score na tela."""
    from dashboard import figuras as fig

    m = pd.DataFrame({"dinamismo": [1.0, -1.0], "tensao": [1.0, -1.0], c.M_MOV: [500, 300],
                      c.M_SAIDA_VOL: [0.6, 0.3], c.M_GAP_SAL: [0.9, 1.0], "motor": ["a", "b"],
                      "quadrante": [c.Q_PRESSAO, c.Q_ESTAGNACAO]})
    figura = fig.construir_matriz(m, pd.Series(["x", "y"]))
    assert all(t.marker.symbol is None for t in figura.data)
    eixos = f"{figura.layout.xaxis.title.text} {figura.layout.yaxis.title.text}"
    assert "cresce" in eixos and "equipe" in eixos and "z" not in eixos.replace("cresce", "")
    assert figura.layout.xaxis.showticklabels is False


def test_gap_salarial_em_palavras():
    """M3.C3: "gap 0,94" vira "6% abaixo"."""
    assert c.fmt_gap(0.94) == "6% abaixo"
    assert c.fmt_gap(1.03) == "3% acima"
    assert c.fmt_gap(float("nan")) == "—"
    assert c.fmt_metrica(c.M_GAP_SAL, 0.94) == "6% abaixo"


def test_no_maximo_quatro_indicadores_principais():
    assert len(c.KPIS_PADRAO) <= 4
