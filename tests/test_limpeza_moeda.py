"""Testes de propriedade da conversão monetária do Limpador (tarefa 4.2).

Validam, com Hypothesis (mín. 100 exemplos por propriedade), o comportamento de
`brl_para_float` e `limpar_moeda` de `src/limpeza.py`:

- Property 5: round-trip de conversão monetária BR ↔ float (R2.1, R2.3).
- Property 6: valores inválidos e o marcador ``"-"`` tornam-se ausentes (NaN)
  com contagem correta de não convertidos (R2.2, R2.4).

Observações de projeto:
- `brl_para_float` arredonda a 2 casas decimais; portanto o round-trip é exato
  para números já com 2 casas decimais.
- Em `limpar_moeda`, o marcador ``"-"`` e a string vazia são tratados como
  *ausência de origem* (não como falha de conversão): viram NaN, mas não entram
  na contagem de valores não convertidos. A contagem reportada corresponde às
  posições genuinamente inválidas (não conversíveis, exceto ``"-"``/vazio),
  conforme R2.2.
"""

from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.limpeza import MARCADOR_AUSENTE, brl_para_float, limpar_moeda


def _formatar_br(valor: float, *, com_milhar: bool) -> str:
    """Formata um float com 2 casas no padrão brasileiro.

    Decimal com vírgula; opcionalmente com ponto como separador de milhar
    (ex.: ``1234.56`` → ``"1.234,56"`` ou ``"1234,56"``).
    """
    negativo = valor < 0
    inteiro = int(round(abs(valor) * 100))
    centavos = inteiro % 100
    parte_inteira = inteiro // 100

    if com_milhar:
        grupos = f"{parte_inteira:,}".replace(",", ".")
    else:
        grupos = str(parte_inteira)

    texto = f"{grupos},{centavos:02d}"
    return f"-{texto}" if negativo else texto


# Números com, no máximo, 2 casas decimais (o domínio da conversão monetária).
_numeros_2_casas = st.decimals(
    min_value=-1_000_000,
    max_value=1_000_000,
    places=2,
    allow_nan=False,
    allow_infinity=False,
).map(lambda d: round(float(d), 2))


# Property 5 -----------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 5: Round-trip de conversão monetária BR ↔ float
@given(valor=_numeros_2_casas, com_milhar=st.booleans())
@settings(max_examples=100)
def test_prop5_round_trip_moeda_br(valor: float, com_milhar: bool) -> None:
    """Formatar no padrão BR e reconverter recupera o valor (2 casas).

    Validates: Requirements 2.1, 2.3
    """
    texto_br = _formatar_br(valor, com_milhar=com_milhar)
    reconvertido = brl_para_float(texto_br)

    assert not math.isnan(reconvertido)
    # Precisão de 2 casas decimais (R2.1/R2.3): comparação exata após round.
    assert reconvertido == round(valor, 2)


# Feature: datathon-caged-sc-pipeline, Property 5: Round-trip de conversão monetária BR ↔ float
@given(valor=_numeros_2_casas)
@settings(max_examples=100)
def test_prop5_round_trip_via_limpar_moeda(valor: float) -> None:
    """O round-trip também vale quando aplicado via `limpar_moeda` numa coluna.

    Validates: Requirements 2.1, 2.3
    """
    texto_br = _formatar_br(valor, com_milhar=True)
    df = pd.DataFrame({"salário": [texto_br]})

    convertido, falhas = limpar_moeda(df, ["salário"])

    assert convertido["salário"].iloc[0] == round(valor, 2)
    # Um valor BR válido não gera falha de conversão.
    assert falhas == []


# Property 6 -----------------------------------------------------------------

# Entradas inválidas (não conversíveis) que NÃO são o marcador "-" nem vazias.
_strings_invalidas = st.text(min_size=1, max_size=8).filter(
    lambda s: brl_para_float(s) != brl_para_float(s)  # resultado é NaN
    and s.strip() not in ("", MARCADOR_AUSENTE)
)


@st.composite
def _sequencias_mistas(draw: st.DrawFn) -> tuple[list[object], list[str]]:
    """Gera uma sequência misturando valores válidos, inválidos e ``"-"``.

    Retorna a lista de valores de origem e a lista de rótulos por posição,
    em que cada rótulo é um de: ``"valido"``, ``"invalido"`` ou ``"marcador"``.
    """
    tamanho = draw(st.integers(min_value=0, max_value=12))
    valores: list[object] = []
    rotulos: list[str] = []

    for _ in range(tamanho):
        tipo = draw(st.sampled_from(["valido", "invalido", "marcador"]))
        if tipo == "valido":
            numero = draw(_numeros_2_casas)
            com_milhar = draw(st.booleans())
            valores.append(_formatar_br(numero, com_milhar=com_milhar))
        elif tipo == "invalido":
            valores.append(draw(_strings_invalidas))
        else:  # marcador "-"
            valores.append(MARCADOR_AUSENTE)
        rotulos.append(tipo)

    return valores, rotulos


# Feature: datathon-caged-sc-pipeline, Property 6: Valores inválidos e `-` tornam-se ausentes com contagem correta
@given(dados=_sequencias_mistas())
@settings(max_examples=100)
def test_prop6_invalidos_e_marcador_viram_nan_com_contagem(
    dados: tuple[list[object], list[str]],
) -> None:
    """NaN aparece exatamente nas posições inválidas/``"-"``; contagem correta.

    - Posições válidas são preservadas (não viram NaN).
    - Posições inválidas e o marcador ``"-"`` viram NaN (R2.2, R2.4).
    - A contagem de não convertidos reportada é igual ao número de posições
      genuinamente inválidas (não conversíveis, exceto ``"-"``), conforme R2.2.

    Validates: Requirements 2.2, 2.4
    """
    valores, rotulos = dados
    df = pd.DataFrame({"salário": valores})

    convertido, falhas = limpar_moeda(df, ["salário"])
    serie = convertido["salário"]

    for i, rotulo in enumerate(rotulos):
        if rotulo == "valido":
            # Valores válidos nunca viram NaN.
            assert not pd.isna(serie.iloc[i])
        else:
            # Inválidos e o marcador "-" viram NaN (R2.2, R2.4).
            assert pd.isna(serie.iloc[i])

    # Contagem reportada = posições genuinamente inválidas (R2.2);
    # o marcador "-" conta como ausência de origem, não como falha.
    esperado_invalidos = sum(1 for r in rotulos if r == "invalido")
    total_reportado = sum(f.quantidade for f in falhas)
    assert total_reportado == esperado_invalidos
