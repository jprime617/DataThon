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
