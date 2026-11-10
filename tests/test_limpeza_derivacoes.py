"""Testes da coluna ordinal de escolaridade derivada pelo Limpador.

`graudeinstrução` tem duas vidas no pipeline: R2.5 manda decodificá-la para o
rótulo legível, e a dispersão renda × escolaridade (R7.4) precisa dela como
**número ordenável**. Uma coluna não faz as duas coisas, por isso o Limpador
deriva uma companheira numérica a partir do código cru, antes da decodificação.

Estes testes travam esse contrato: o nível sai na ordem certa, a derivação
acontece antes da decodificação, e código desconhecido vira ausente.
"""

from __future__ import annotations

import math

import pandas as pd

from src.limpeza import (
    COLUNA_ESCOLARIDADE_ORDINAL,
    COLUNA_GRAU_INSTRUCAO,
    derivar_escolaridade_ordinal,
    limpar,
)

# Mapas de domínio mínimos: o suficiente para a decodificação acontecer.
_MAPAS = {"graudeinstrução": {7: "Médio Completo", 9: "Superior Completo"}}


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
def test_limpar_deriva_o_numero_antes_de_decodificar_o_rotulo():
    """Depois de `limpar`, convivem o rótulo legível e o nível ordinal.

    É a regressão que importa: se a derivação rodasse *depois* da decodificação,
    ela leria ``"Médio Completo"`` em vez de ``7`` e produziria NaN, deixando a
    dispersão renda × escolaridade sem eixo.
    """
    caged = pd.DataFrame(
        {
            "competênciamov": ["202509", "202510"],
            COLUNA_GRAU_INSTRUCAO: ["7", "9"],
        }
    )
    municipios = pd.DataFrame({"Código": ["4200051"]})

    resultado = limpar(caged, municipios, _MAPAS)

    # Rótulo legível na coluna original (R2.5).
    assert resultado.caged[COLUNA_GRAU_INSTRUCAO].tolist() == [
        "Médio Completo",
        "Superior Completo",
    ]
    # Número utilizável na coluna derivada (R4.7).
    assert resultado.caged[COLUNA_ESCOLARIDADE_ORDINAL].tolist() == [7.0, 9.0]
    assert not any(math.isnan(v) for v in resultado.caged[COLUNA_ESCOLARIDADE_ORDINAL])
