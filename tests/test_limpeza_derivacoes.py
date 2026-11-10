"""Testes das colunas derivadas do Limpador: estoque base e escolaridade ordinal.

`tamestabjan` e `graudeinstrução` têm duas vidas no pipeline: R2.5 manda
decodificá-las para rótulo legível, e R4.4/R4.7 precisam delas como **número**
(denominador do Turnover e eixo da dispersão renda × escolaridade). Uma coluna
não faz as duas coisas, por isso o Limpador deriva companheiras numéricas a
partir dos códigos crus, antes da decodificação.

Estes testes travam esse contrato: o número sai certo, a derivação acontece
antes da decodificação, e código desconhecido/faixa sem tamanho vira ausente.
"""

from __future__ import annotations

import math

import pandas as pd

from src.limpeza import (
    COLUNA_ESCOLARIDADE_ORDINAL,
    COLUNA_ESTOQUE_BASE,
    COLUNA_GRAU_INSTRUCAO,
    COLUNA_TAM_ESTAB_JAN,
    derivar_escolaridade_ordinal,
    derivar_estoque_base,
    limpar,
)

# Mapas de domínio mínimos: o suficiente para a decodificação acontecer.
_MAPAS = {
    "tamestabjan": {4: "De 10 a 19", 5: "De 20 a 49"},
    "graudeinstrução": {7: "Médio Completo", 9: "Superior Completo"},
}


# ---------------------------------------------------------------------------
# Estoque base (R4.4)
# ---------------------------------------------------------------------------
def test_estoque_base_usa_ponto_medio_da_faixa():
    """Cada código de faixa vira o ponto médio em vínculos, não o próprio código."""
    df = pd.DataFrame({COLUNA_TAM_ESTAB_JAN: ["2", "4", "5", "7", "10"]})
    resultado = derivar_estoque_base(df)
    assert resultado[COLUNA_ESTOQUE_BASE].tolist() == [2.5, 14.5, 34.5, 174.5, 1500.0]


def test_estoque_base_e_ausente_para_faixas_sem_tamanho():
    """'Zero', 'Inválido', 'Ignorado' e códigos desconhecidos viram NaN (R4.5)."""
    df = pd.DataFrame({COLUNA_TAM_ESTAB_JAN: ["1", "98", "99", "77", "", None]})
    resultado = derivar_estoque_base(df)
    assert resultado[COLUNA_ESTOQUE_BASE].isna().all()


def test_estoque_base_aceita_codigo_como_numero_ou_texto():
    """O código chega como texto (`dtype=str` na ingestão) ou como número."""
    texto = derivar_estoque_base(pd.DataFrame({COLUNA_TAM_ESTAB_JAN: ["5"]}))
    numero = derivar_estoque_base(pd.DataFrame({COLUNA_TAM_ESTAB_JAN: [5]}))
    flutuante = derivar_estoque_base(pd.DataFrame({COLUNA_TAM_ESTAB_JAN: [5.0]}))
    assert (
        texto[COLUNA_ESTOQUE_BASE][0]
        == numero[COLUNA_ESTOQUE_BASE][0]
        == flutuante[COLUNA_ESTOQUE_BASE][0]
        == 34.5
    )


def test_estoque_base_ignora_df_sem_a_coluna():
    """Sem `tamestabjan` a cópia volta intacta, sem quebrar o pipeline."""
    df = pd.DataFrame({"outra": [1, 2]})
    resultado = derivar_estoque_base(df)
    assert COLUNA_ESTOQUE_BASE not in resultado.columns
    assert resultado.equals(df)


# ---------------------------------------------------------------------------
# Escolaridade ordinal (R4.7)
# ---------------------------------------------------------------------------
def test_escolaridade_ordinal_preserva_a_ordem_do_dicionario():
    """Os códigos 1..11 são ordinais; 80 (pós) entra entre superior e mestrado."""
    df = pd.DataFrame({COLUNA_GRAU_INSTRUCAO: ["1", "7", "9", "80", "10", "11"]})
    resultado = derivar_escolaridade_ordinal(df)
    niveis = resultado[COLUNA_ESCOLARIDADE_ORDINAL].tolist()
    assert niveis == [1.0, 7.0, 9.0, 9.5, 10.0, 11.0]
    assert niveis == sorted(niveis), "a escala precisa ser monotônica"


def test_escolaridade_ordinal_e_ausente_para_codigo_desconhecido():
    df = pd.DataFrame({COLUNA_GRAU_INSTRUCAO: ["0", "42", "", None]})
    resultado = derivar_escolaridade_ordinal(df)
    assert resultado[COLUNA_ESCOLARIDADE_ORDINAL].isna().all()


# ---------------------------------------------------------------------------
# Ordem na orquestração: derivar ANTES de decodificar
# ---------------------------------------------------------------------------
def test_limpar_deriva_os_numeros_antes_de_decodificar_os_rotulos():
    """Depois de `limpar`, convivem o rótulo legível e o número derivado.

    É a regressão que importa: se a derivação rodasse *depois* da decodificação,
    ela leria ``"De 20 a 49"`` em vez de ``5`` e produziria NaN — que era a causa
    do Turnover ausente em todos os recortes.
    """
    caged = pd.DataFrame(
        {
            "competênciamov": ["202509", "202510"],
            COLUNA_TAM_ESTAB_JAN: ["5", "4"],
            COLUNA_GRAU_INSTRUCAO: ["7", "9"],
        }
    )
    municipios = pd.DataFrame({"Código": ["4200051"]})

    resultado = limpar(caged, municipios, _MAPAS)

    # Rótulos legíveis nas colunas originais (R2.5).
    assert resultado.caged[COLUNA_TAM_ESTAB_JAN].tolist() == ["De 20 a 49", "De 10 a 19"]
    assert resultado.caged[COLUNA_GRAU_INSTRUCAO].tolist() == [
        "Médio Completo",
        "Superior Completo",
    ]
    # Números utilizáveis nas colunas derivadas (R4.4, R4.7).
    assert resultado.caged[COLUNA_ESTOQUE_BASE].tolist() == [34.5, 14.5]
    assert resultado.caged[COLUNA_ESCOLARIDADE_ORDINAL].tolist() == [7.0, 9.0]
    assert not any(math.isnan(v) for v in resultado.caged[COLUNA_ESTOQUE_BASE])
