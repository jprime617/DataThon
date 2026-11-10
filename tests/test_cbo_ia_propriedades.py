"""Testes de propriedade do Classificador_de_CBO (tarefa 8.2).

Implementam as propriedades 19 e 20 do design com Hypothesis (mín. 100 exemplos,
perfil `datathon` carregado em `conftest.py`), com tag de rastreabilidade
obrigatória por propriedade:

- Property 19: Extração de CBOs retorna distintos não vazios — R5.1
- Property 20: Loteamento respeita o limite de 100 e preserva o conjunto — R5.3

A propriedade 19 gera DataFrames CAGED-like com a coluna `cbo2002ocupação`
misturando códigos válidos (texto/numéricos), nulos (``None``/``NaN``) e vazios,
e verifica que `extrair_cbos` retorna apenas códigos distintos, não nulos e não
vazios. A propriedade 20 gera listas de códigos e um tamanho de lote, e verifica
que `lotear` produz lotes de no máximo `tamanho` elementos, disjuntos, cuja
concatenação na ordem reproduz exatamente a lista original.
"""

from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.cbo_ia import COLUNA_CBO, TAMANHO_LOTE, extrair_cbos, lotear

# ---------------------------------------------------------------------------
# Estratégias auxiliares.
# ---------------------------------------------------------------------------

# Códigos CBO válidos como texto (dígitos, sem espaços ao redor).
_CBO_TEXTO = st.text(
    alphabet="0123456789", min_size=1, max_size=6
)

# Códigos CBO válidos como inteiros (lidos numericamente de um CSV).
_CBO_INT = st.integers(min_value=0, max_value=999_999)

# Valores que devem ser descartados por `extrair_cbos` (nulos ou vazios).
_CBO_DESCARTAVEL = st.sampled_from([None, float("nan"), "", "   "])

# Um elemento da coluna: código válido (texto ou int) ou valor descartável.
_ELEMENTO_COLUNA = st.one_of(_CBO_TEXTO, _CBO_INT, _CBO_DESCARTAVEL)


def _eh_descartavel(valor: object) -> bool:
    """Replica o critério de descarte de `extrair_cbos` (nulo/NaN/vazio)."""
    if valor is None:
        return True
    if isinstance(valor, float) and math.isnan(valor):
        return True
    if isinstance(valor, str) and valor.strip() == "":
        return True
    return False


# ---------------------------------------------------------------------------
# Property 19: Extração de CBOs retorna distintos não vazios.
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 19: Extração de CBOs retorna distintos não vazios
@settings(max_examples=100)
@given(valores=st.lists(_ELEMENTO_COLUNA, min_size=0, max_size=50))
def test_prop19_extracao_cbos_retorna_distintos_nao_vazios(valores):
    # Feature: datathon-caged-sc-pipeline, Property 19: Extração de CBOs retorna distintos não vazios
    # Validates: Requirements 5.1
    df = pd.DataFrame({COLUNA_CBO: pd.Series(valores, dtype=object)})

    resultado = extrair_cbos(df)

    # Resultado é uma lista de strings, sem nulos e sem vazios.
    assert isinstance(resultado, list)
    for codigo in resultado:
        assert isinstance(codigo, str)
        assert codigo != ""
        assert codigo.strip() != ""

    # Os códigos retornados são distintos (cada um aparece exatamente uma vez).
    assert len(resultado) == len(set(resultado))

    # Todo valor descartável da entrada NÃO contribui com um código;
    # todo código distinto não descartável da entrada aparece no resultado.
    esperados: list[str] = []
    vistos: set[str] = set()
    for valor in valores:
        if _eh_descartavel(valor):
            continue
        # Normalização equivalente à da implementação para códigos válidos.
        if isinstance(valor, int):
            codigo = str(valor)
        else:
            codigo = str(valor).strip()
        if codigo in vistos:
            continue
        vistos.add(codigo)
        esperados.append(codigo)

    assert resultado == esperados


# ---------------------------------------------------------------------------
# Property 20: Loteamento respeita o limite de 100 e preserva o conjunto.
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 20: Loteamento respeita o limite de 100 e preserva o conjunto
@settings(max_examples=100)
@given(
    itens=st.lists(_CBO_TEXTO, min_size=0, max_size=350),
    tamanho=st.integers(min_value=1, max_value=TAMANHO_LOTE),
)
def test_prop20_loteamento_respeita_limite_e_preserva_conjunto(itens, tamanho):
    # Feature: datathon-caged-sc-pipeline, Property 20: Loteamento respeita o limite de 100 e preserva o conjunto
    # Validates: Requirements 5.3
    lotes = lotear(itens, tamanho)

    # Cada lote respeita o limite máximo (≤ tamanho, com teto em 100 — R5.3).
    assert tamanho <= TAMANHO_LOTE
    for lote in lotes:
        assert 0 < len(lote) <= tamanho
        assert len(lote) <= TAMANHO_LOTE

    # A concatenação dos lotes, na ordem, reproduz exatamente a lista original.
    concatenado: list[str] = [item for lote in lotes for item in lote]
    assert concatenado == itens

    # Lista vazia produz nenhum lote; caso contrário o número de lotes é o teto
    # da divisão (lotes disjuntos que cobrem toda a lista sem sobreposição).
    assert len(lotes) == math.ceil(len(itens) / tamanho)
