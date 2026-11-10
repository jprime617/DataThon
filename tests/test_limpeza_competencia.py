"""Teste de propriedade do filtro de competência do Limpador (tarefa 4.6).

Valida, com Hypothesis (mín. 100 exemplos), o comportamento de
`filtrar_competencia` de `src/limpeza.py`:

- Property 8: filtro de competência particiona corretamente pelo intervalo
  inclusivo (R2.8, R2.9).

A `competênciamov` pode chegar à função como ``str`` (``"202509"``), ``int``
(``202509``) ou ``float`` (``202509.0``), além de valores ausentes/não numéricos
(``None``, ``NaN``, ``"-"``, texto arbitrário, floats não inteiros). Todos os
registros fora do intervalo fechado ``[202509, 202608]`` — inclusive os
ausentes/não numéricos — devem ser excluídos e contabilizados.

Propriedades verificadas (partição correta):
- os mantidos são exatamente os registros cuja competência é um AAAAMM inteiro
  dentro de ``[inicio, fim]``;
- mantidos e excluídos são disjuntos e sua união é o conjunto original
  (``len(mantidos) + qtde_excluidos == len(df)``);
- a contagem de excluídos reportada é igual ao número de registros fora do
  intervalo (incluindo ausentes/não numéricos).
"""

from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.limpeza import (
    COLUNA_COMPETENCIA,
    COMPETENCIA_FIM,
    COMPETENCIA_INICIO,
    MARCADOR_AUSENTE,
    filtrar_competencia,
)


def _competencia_valida_int(valor: object, inicio: int, fim: int) -> bool:
    """Replica, de forma independente, o critério de inclusão esperado.

    Um registro é mantido somente quando sua competência representa um inteiro
    AAAAMM dentro do intervalo fechado ``[inicio, fim]``. Valores ausentes
    (``None``/``NaN``), o marcador ``"-"``, textos não numéricos e floats não
    inteiros ficam fora do intervalo (R2.9).
    """
    if valor is None:
        return False
    if isinstance(valor, bool):
        return False
    if isinstance(valor, int):
        return inicio <= valor <= fim
    if isinstance(valor, float):
        if math.isnan(valor) or not valor.is_integer():
            return False
        return inicio <= int(valor) <= fim
    if isinstance(valor, str):
        texto = valor.strip()
        if texto == "" or texto == MARCADOR_AUSENTE:
            return False
        try:
            numero = float(texto)
        except ValueError:
            return False
        if not numero.is_integer():
            return False
        return inicio <= int(numero) <= fim
    return False


# Competências como inteiros: cobrem tanto o intervalo-alvo quanto o entorno
# (limites e valores fora, acima e abaixo).
_competencias_int = st.integers(min_value=200001, max_value=203012)


def _como_str(valor: int) -> str:
    return str(valor)


def _como_float(valor: int) -> float:
    return float(valor)


# Uma competência válida pode chegar como int, str numérica ou float inteiro.
_competencia_numerica = st.one_of(
    _competencias_int,
    _competencias_int.map(_como_str),
    _competencias_int.map(_como_float),
)

# Valores de competência ausentes ou não numéricos (sempre excluídos, R2.9).
_competencia_ausente = st.one_of(
    st.none(),
    st.just(float("nan")),
    st.just(MARCADOR_AUSENTE),
    st.just(""),
    st.just("   "),
    st.text(min_size=1, max_size=6).filter(
        lambda s: not s.strip().replace(".", "", 1).isdigit()
    ),
    # floats não inteiros não representam um AAAAMM válido.
    st.floats(min_value=200001.1, max_value=203012.9).filter(
        lambda f: not float(f).is_integer()
    ),
)

_qualquer_competencia = st.one_of(_competencia_numerica, _competencia_ausente)


# Feature: datathon-caged-sc-pipeline, Property 8: Filtro de competência particiona corretamente pelo intervalo inclusivo
@given(competencias=st.lists(_qualquer_competencia, max_size=40))
@settings(max_examples=100)
def test_prop8_filtro_competencia_particiona_intervalo_inclusivo(
    competencias: list[object],
) -> None:
    """Mantidos = intervalo inclusivo; partição disjunta; contagem exata.

    - Os registros mantidos são exatamente os com competência inteira AAAAMM em
      ``[202509, 202608]`` (R2.8).
    - Mantidos e excluídos são disjuntos e sua união é o conjunto original:
      ``len(df_filtrado) + qtde_excluidos == len(df)`` (R2.9).
    - A contagem de excluídos reportada é igual ao número de registros fora do
      intervalo, incluindo ausentes/não numéricos (R2.9).

    Validates: Requirements 2.8, 2.9
    """
    # Uma coluna acompanhante (índice posicional) permite verificar quais linhas
    # exatamente foram mantidas, não apenas a quantidade.
    df = pd.DataFrame(
        {
            COLUNA_COMPETENCIA: competencias,
            "_pos": list(range(len(competencias))),
        }
    )

    df_filtrado, qtde_excluidos = filtrar_competencia(df)

    esperado_mantidos = [
        i
        for i, c in enumerate(competencias)
        if _competencia_valida_int(c, COMPETENCIA_INICIO, COMPETENCIA_FIM)
    ]

    # Mantidos são exatamente os esperados pelo intervalo inclusivo (R2.8).
    assert list(df_filtrado["_pos"]) == esperado_mantidos

    # Partição disjunta cuja união é o conjunto original (R2.9).
    assert len(df_filtrado) + qtde_excluidos == len(df)

    # Contagem de excluídos = registros fora do intervalo (R2.9).
    assert qtde_excluidos == len(competencias) - len(esperado_mantidos)


# Feature: datathon-caged-sc-pipeline, Property 8: Filtro de competência particiona corretamente pelo intervalo inclusivo
@given(
    inicio=_competencias_int,
    extra=st.integers(min_value=0, max_value=24),
)
@settings(max_examples=100)
def test_prop8_limites_do_intervalo_sao_inclusivos(
    inicio: int, extra: int
) -> None:
    """Os limites ``inicio`` e ``fim`` são mantidos (intervalo fechado).

    Constrói um intervalo arbitrário ``[inicio, fim]`` e verifica que ambos os
    extremos são mantidos, enquanto ``inicio - 1`` e ``fim + 1`` são excluídos.

    Validates: Requirements 2.8, 2.9
    """
    fim = inicio + extra
    competencias = [inicio - 1, inicio, fim, fim + 1]
    df = pd.DataFrame(
        {
            COLUNA_COMPETENCIA: competencias,
            "_pos": list(range(len(competencias))),
        }
    )

    df_filtrado, qtde_excluidos = filtrar_competencia(df, inicio=inicio, fim=fim)

    mantidos = set(df_filtrado["_pos"])
    # posições 1 (inicio) e 2 (fim) são inclusivas; 0 e 3 ficam de fora.
    assert mantidos == {1, 2}
    assert qtde_excluidos == 2
    assert len(df_filtrado) + qtde_excluidos == len(df)
