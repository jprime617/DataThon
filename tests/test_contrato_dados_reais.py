"""Contrato de formato dos arquivos de origem reais.

Os testes de unidade e o teste de integração rodam sobre fixtures. Fixture é
uma *afirmação sobre o formato dos dados* — e, quando essa afirmação diverge do
arquivo real, a suíte fica verde enquanto o pipeline produz números errados.
Foi exatamente o que aconteceu: o fixture escrevia os indicadores municipais em
formato brasileiro (``"0,750"``) enquanto o arquivo do IBGE usa ponto decimal
(``0.750``), de modo que a conversão errada passou despercebida.

Este módulo fecha essa lacuna lendo **apenas o cabeçalho e as primeiras linhas**
dos arquivos em `Dados/` e afirmando as premissas de formato das quais o
Limpador depende. É barato (nada de carregar 3,4 milhões de linhas) e falha alto
no dia em que a origem mudar de formato.

Os testes são pulados quando os arquivos de origem não estão presentes, para que
a suíte continue executável em ambientes sem os dados (CI, clone limpo).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.limpeza import (
    COLUNAS_INDICADORES_MUNICIPIOS,
    limpar_indicadores_municipios,
)

# Coluna de faixa de tamanho do estabelecimento no CAGED (domínio de R2.5).
COLUNA_TAM_ESTAB_JAN = "tamestabjan"

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_CAGED = RAIZ / "Dados" / "Novo_Caged_MOV_Limpo.csv"
CAMINHO_MUNICIPIOS = RAIZ / "Dados" / "Municipios_SC_limpo.csv"

pytestmark = pytest.mark.skipif(
    not (CAMINHO_CAGED.is_file() and CAMINHO_MUNICIPIOS.is_file()),
    reason="arquivos de origem ausentes em Dados/",
)


def _amostra_caged(linhas: int = 50) -> pd.DataFrame:
    """Lê as primeiras linhas do CAGED com os parâmetros reais de leitura."""
    return pd.read_csv(
        CAMINHO_CAGED, sep=";", encoding="utf-8", dtype=str, nrows=linhas
    )


def _municipios() -> pd.DataFrame:
    return pd.read_csv(CAMINHO_MUNICIPIOS, sep=",", dtype=str)


# ---------------------------------------------------------------------------
# CAGED: separador ';', decimal ',' nas colunas monetárias
# ---------------------------------------------------------------------------
def test_caged_usa_virgula_decimal_no_salario():
    """O CAGED é mesmo brasileiro: `salário` usa vírgula decimal (R2.1)."""
    amostra = _amostra_caged()
    salarios = amostra["salário"].dropna().astype(str)
    assert not salarios.empty
    assert salarios.str.contains(",").any(), (
        "nenhum salário com vírgula decimal nas primeiras linhas — o CAGED "
        "mudou de formato e `brl_para_float` deixou de ser a conversão correta"
    )


def test_caged_tem_tamestabjan_como_codigo_de_faixa():
    """`tamestabjan` é código de faixa (1–10, 98, 99), não contagem de vínculos.

    É a premissa que sustenta a decodificação de domínio de R2.5 — e o motivo
    de a coluna não servir como denominador do Turnover: código de faixa não é
    contagem de vínculos.
    """
    amostra = _amostra_caged(500)
    codigos = pd.to_numeric(amostra[COLUNA_TAM_ESTAB_JAN], errors="coerce").dropna()
    assert not codigos.empty
    assert codigos.isin([*range(1, 11), 98, 99]).all(), (
        f"códigos fora do domínio de faixa: {sorted(set(codigos) - set(range(1, 11)) - {98, 99})}"
    )


# ---------------------------------------------------------------------------
# Municípios: ponto decimal (NÃO formato brasileiro)
# ---------------------------------------------------------------------------
def test_municipios_usam_ponto_decimal_nos_indicadores():
    """Os indicadores do IBGE usam ponto decimal — nunca vírgula (R2.3).

    Se esta premissa cair, `limpar_indicadores_municipios` precisa voltar a usar
    a conversão brasileira; hoje ela usa `pandas.to_numeric`, que leria
    ``"0,750"`` como ausente.
    """
    municipios = _municipios()
    for coluna in COLUNAS_INDICADORES_MUNICIPIOS:
        valores = municipios[coluna].dropna().astype(str)
        assert not valores.str.contains(",").any(), (
            f"coluna {coluna!r} contém vírgula decimal — o arquivo mudou para "
            "formato brasileiro e a conversão precisa acompanhar"
        )


def test_idhm_real_permanece_na_escala_zero_um_apos_limpeza():
    """O IDHM sobrevive à limpeza dentro de [0, 1] (R2.3).

    Esta é a asserção que teria apanhado a corrupção por `brl_para_float`, que
    transformava ``0.809`` em ``809.0`` ao remover o ponto como se fosse
    separador de milhar.
    """
    limpo, _ = limpar_indicadores_municipios(_municipios())
    idhm = limpo[COLUNAS_INDICADORES_MUNICIPIOS[1]].dropna()
    assert not idhm.empty
    assert (idhm > 0).all() and (idhm <= 1).all(), (
        f"IDHM fora de [0,1]: mín={idhm.min()}, máx={idhm.max()}"
    )


def test_pib_per_capita_real_mantem_ordem_de_grandeza():
    """O PIB per capita fica na casa de milhares/dezenas de milhares de reais."""
    limpo, _ = limpar_indicadores_municipios(_municipios())
    pib = limpo[COLUNAS_INDICADORES_MUNICIPIOS[2]].dropna()
    assert not pib.empty
    # Nenhum município brasileiro tem PIB per capita acima de R$ 1 milhão.
    assert pib.max() < 1_000_000, (
        f"PIB per capita máximo implausível: {pib.max():,.2f} — provável perda "
        "do separador decimal na conversão"
    )


def test_populacao_estimada_real_e_plausivel():
    """A população estimada 2026 fica entre centenas e ~700 mil habitantes."""
    limpo, _ = limpar_indicadores_municipios(_municipios())
    pop = limpo[COLUNAS_INDICADORES_MUNICIPIOS[0]].dropna()
    assert not pop.empty
    assert pop.min() > 0
    # Joinville, o maior município de SC, tem ~674 mil habitantes.
    assert pop.max() < 2_000_000, f"população máxima implausível: {pop.max():,.0f}"
