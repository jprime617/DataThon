"""Regras do Lote D (P1 + ANA-04) do plano da banca."""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard import comum as c
from dashboard import narrativa as nar
from dashboard import regras as r
from tests.test_dashboard_metricas import _celula, _df

MESES_12 = [f"2025{m:02d}" for m in range(9, 13)] + [f"2026{m:02d}" for m in range(1, 9)]


# --- TAX-02: selo "Expansão concentrada" ---------------------------------------


@pytest.mark.parametrize("saldo, fm, nm, fu, nu, esperado", [
    (100, 0.40, 12, 0.10, 5, True),     # um mês com 40% do saldo positivo (borda conta)
    (100, 0.39, 12, 0.80, 5, True),     # um município com 80% (borda conta)
    (100, 0.39, 12, 0.79, 5, False),
    (100, 0.90, 3, 0.10, 5, False),     # poucos meses no filtro: 1 mês com 40% é o normal
    (100, 0.10, 12, 1.00, 1, False),    # um município só (ficha de município): regra não se aplica
    (-50, 0.90, 12, 1.00, 5, False),    # só vale para quem abriu vagas
    (0, 0.90, 12, 1.00, 5, False),
])
def test_regra_da_expansao_concentrada(saldo, fm, nm, fu, nu, esperado):
    assert r.expansao_concentrada(saldo, fm, nm, fu, nu) is esperado


def _grupo_por_mes(saldos: list[int], **extra) -> list[dict]:
    return [_celula(mes=m, admissoes=max(s, 0) + 10, desligamentos=max(-s, 0) + 10, **extra)
            for m, s in zip(MESES_12, saldos)]


def test_mes_com_40_por_cento_do_saldo_positivo_acende_o_selo():
    # 11 meses com +10 e um mês com +80: 80 / 190 = 42% do saldo positivo.
    df = _df(*_grupo_por_mes([10] * 11 + [80]))
    conc = c.concentracao_saldo(df, ["regiao", "setor"]).iloc[0]
    assert conc["fracao_mes"] == pytest.approx(80 / 190)
    assert conc["mes_pico"] == "202608"
    assert bool(conc["concentrada"])


def test_denominador_e_o_saldo_positivo_nao_o_liquido():
    """Município +44 e outros −38: com o saldo líquido (6) daria 733% e acenderia sempre."""
    df = _df(_celula(admissoes=44), _celula(municipio="420540", municipio_nome="Florianópolis", desligamentos=20),
             _celula(municipio="420820", municipio_nome="Itajaí", desligamentos=18),
             _celula(municipio="421130", municipio_nome="Navegantes", admissoes=40))
    conc = c.concentracao_saldo(df, ["regiao", "setor"]).iloc[0]
    assert conc["fracao_municipio"] == pytest.approx(44 / 84)
    assert not bool(conc["concentrada"])


def test_crescimento_espalhado_nao_acende():
    df = _df(*_grupo_por_mes([10] * 12))
    assert not bool(c.concentracao_saldo(df, ["regiao", "setor"]).iloc[0]["concentrada"])


def test_selo_vai_para_a_matriz_e_para_o_texto():
    df = _df(*_grupo_por_mes([10] * 11 + [300]),
             *_grupo_por_mes([10] * 12, setor="Têxtil"))
    por = ["regiao", "setor"]
    m = c.anexar_concentracao(c.agregar_metricas(df, por), df, por).set_index("setor")
    assert bool(m.loc["Metalurgia e produtos de metal", "concentrada"])
    assert not bool(m.loc["Têxtil", "concentrada"])
    texto = nar.texto_concentrada(m.loc["Metalurgia e produtos de metal"])
    assert texto.startswith(f"**{c.SELO_CONCENTRADA}**") and "ago/26" in texto
    assert nar.texto_concentrada(m.loc["Têxtil"]) == ""


def test_concentracao_de_recorte_vazio_nao_quebra():
    vazio = _df(_celula()).iloc[0:0]
    assert c.concentracao_saldo(vazio, ["regiao", "setor"]).empty
    m = c.anexar_concentracao(c.agregar_metricas(vazio, ["regiao", "setor"]), vazio, ["regiao", "setor"])
    assert "concentrada" in m.columns and m.empty
