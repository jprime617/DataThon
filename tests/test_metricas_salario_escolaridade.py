"""Testes de propriedade de salário e escolaridade do Calculador_de_Metricas (tarefa 7.6).

Valida, com Hypothesis (mín. 100 exemplos), duas métricas de `src/metricas.py`:

- Property 16: Salário médio ignora ausentes e fica entre os extremos (R4.6).
  Para qualquer vetor de salários com valores ausentes, o salário médio (de
  admissão ou de desligamento) é igual à média dos valores não ausentes e está
  entre o menor e o maior valor não ausente; inserir valores ausentes
  adicionais não altera a média.
- Property 17: Distribuição de escolaridade soma ao total (R4.7). Para qualquer
  recorte (movimentação × seção), a soma das contagens por grau de instrução
  dos admitidos é igual ao total de admitidos, e idem para os desligados; as
  proporções de cada grupo somam 1.

LLM e Azure não entram aqui: as funções sob teste são puras sobre DataFrames.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.metricas import (
    CASAS_DECIMAIS_SALARIO,
    COLUNA_CONTAGEM,
    COLUNA_GRAU_INSTRUCAO,
    COLUNA_MOVIMENTACAO,
    COLUNA_PROPORCAO,
    COLUNA_SALARIO,
    COLUNA_SALARIO_MEDIO,
    COLUNA_SALDO_MOVIMENTACAO,
    COLUNA_SECAO,
    MOVIMENTACAO_ADMISSAO,
    MOVIMENTACAO_DESLIGAMENTO,
    SALDO_ADMISSAO,
    SALDO_DESLIGAMENTO,
    distribuicao_escolaridade,
    salario_medio_por_movimentacao,
)

# ---------------------------------------------------------------------------
# Estratégias compartilhadas
# ---------------------------------------------------------------------------

# Movimentações: admissão (+1) e desligamento (-1) são as de interesse; 0 e
# outros códigos devem ser ignorados pelas funções (R4.6, R4.7).
_movimentacoes = st.sampled_from([SALDO_ADMISSAO, SALDO_DESLIGAMENTO, 0, 2])

# Secao_Industrial (seção CNAE): poucas distintas para forçar agrupamentos reais.
_secoes = st.sampled_from(["A", "B", "C"])

# Graus de instrução decodificados; inclui ausentes (NaN) como categoria própria.
_graus = st.sampled_from(
    [
        "Analfabeto",
        "Fundamental Completo",
        "Médio Completo",
        "Superior Completo",
        float("nan"),
    ]
)

# Salários em R$: valores finitos razoáveis, mais ausentes (NaN).
_salario_valido = st.floats(
    min_value=0.0,
    max_value=100_000.0,
    allow_nan=False,
    allow_infinity=False,
)
_salario_ou_ausente = st.one_of(_salario_valido, st.just(float("nan")))


# ---------------------------------------------------------------------------
# Property 16: Salário médio ignora ausentes e fica entre os extremos (R4.6)
# ---------------------------------------------------------------------------


@st.composite
def _movimentacoes_salario(draw: st.DrawFn) -> pd.DataFrame:
    """Gera movimentações com movimentação × seção × salário (podendo ausentes)."""
    n = draw(st.integers(min_value=0, max_value=40))
    movs = draw(st.lists(_movimentacoes, min_size=n, max_size=n))
    secoes = draw(st.lists(_secoes, min_size=n, max_size=n))
    salarios = draw(st.lists(_salario_ou_ausente, min_size=n, max_size=n))
    return pd.DataFrame(
        {
            COLUNA_SALDO_MOVIMENTACAO: movs,
            COLUNA_SECAO: secoes,
            COLUNA_SALARIO: salarios,
        }
    )


# Feature: datathon-caged-sc-pipeline, Property 16: Salário médio ignora ausentes e fica entre os extremos
@given(df=_movimentacoes_salario())
@settings(max_examples=100)
def test_prop16_salario_medio_ignora_ausentes_entre_extremos(
    df: pd.DataFrame,
) -> None:
    """Média por grupo = média dos não ausentes e está entre o mín e o máx.

    - Apenas admissões (+1) e desligamentos (-1) entram; demais movimentações
      são ignoradas.
    - Para cada grupo (movimentação × seção), o salário médio reportado é igual
      à média dos salários não ausentes do grupo (arredondada a 2 casas) e, se
      há ao menos um salário não ausente, está entre o menor e o maior não
      ausente. Grupo totalmente ausente → média NaN (R4.6).

    Validates: Requirements 4.6
    """
    resultado = salario_medio_por_movimentacao(df)

    assert list(resultado.columns) == [
        COLUNA_MOVIMENTACAO,
        COLUNA_SECAO,
        COLUNA_SALARIO_MEDIO,
    ]

    rotulos = {SALDO_ADMISSAO: MOVIMENTACAO_ADMISSAO, SALDO_DESLIGAMENTO: MOVIMENTACAO_DESLIGAMENTO}
    recorte = df[df[COLUNA_SALDO_MOVIMENTACAO].isin(rotulos)]

    if recorte.empty:
        assert resultado.empty
        return

    # Grupos esperados (rótulo de movimentação × seção) calculados à parte.
    grupos_esperados = {
        (rotulos[mov], secao)
        for mov, secao in zip(
            recorte[COLUNA_SALDO_MOVIMENTACAO], recorte[COLUNA_SECAO]
        )
    }
    grupos_resultado = {
        (linha[COLUNA_MOVIMENTACAO], linha[COLUNA_SECAO])
        for _, linha in resultado.iterrows()
    }
    assert grupos_resultado == grupos_esperados

    for _, linha in resultado.iterrows():
        mov_rotulo = linha[COLUNA_MOVIMENTACAO]
        secao = linha[COLUNA_SECAO]
        obtido = linha[COLUNA_SALARIO_MEDIO]

        # Salários do grupo correspondente, apenas não ausentes.
        cod_mov = SALDO_ADMISSAO if mov_rotulo == MOVIMENTACAO_ADMISSAO else SALDO_DESLIGAMENTO
        salarios_grupo = df[
            (df[COLUNA_SALDO_MOVIMENTACAO] == cod_mov) & (df[COLUNA_SECAO] == secao)
        ][COLUNA_SALARIO]
        nao_ausentes = [s for s in salarios_grupo if not math.isnan(s)]

        if not nao_ausentes:
            # Todos ausentes → média NaN (nada a promediar).
            assert math.isnan(obtido)
            continue

        # Oráculo consistente com a implementação: a média é calculada pelo
        # pandas e arredondada a 2 casas com `numpy.round` (round-half-to-even),
        # exatamente como `salario_medio_por_movimentacao` faz com
        # `Series.mean().round(2)`. Usar o `round` embutido do Python aqui
        # divergiria em valores de meia casa (ex.: média 0.005, cujo float fica
        # ligeiramente acima de 0.005: Python arredonda para 0.01, enquanto o
        # pandas/numpy produz 0.0), o que não indica um bug na métrica — apenas
        # modos de arredondamento diferentes para o mesmo contrato de R4.6.
        media_pandas = pd.Series(nao_ausentes, dtype="float64").mean()
        esperado = float(np.round(media_pandas, CASAS_DECIMAIS_SALARIO))
        assert math.isclose(obtido, esperado, rel_tol=1e-9, abs_tol=1e-6)

        # A média (não arredondada) fica entre os extremos dos não ausentes;
        # com o arredondamento permitimos uma pequena folga nas bordas.
        minimo = min(nao_ausentes)
        maximo = max(nao_ausentes)
        assert minimo - 0.01 <= obtido <= maximo + 0.01


# Feature: datathon-caged-sc-pipeline, Property 16: Salário médio ignora ausentes e fica entre os extremos
@given(
    salarios=st.lists(_salario_valido, min_size=1, max_size=30),
    extra_ausentes=st.integers(min_value=0, max_value=20),
)
@settings(max_examples=100)
def test_prop16_inserir_ausentes_nao_altera_media(
    salarios: list[float], extra_ausentes: int
) -> None:
    """Inserir salários ausentes adicionais não altera a média (R4.6).

    Monta um único grupo (admissão × seção "A") com salários válidos; a média
    deve ser a mesma com e sem valores ausentes extras injetados.

    Validates: Requirements 4.6
    """
    base = pd.DataFrame(
        {
            COLUNA_SALDO_MOVIMENTACAO: [SALDO_ADMISSAO] * len(salarios),
            COLUNA_SECAO: ["A"] * len(salarios),
            COLUNA_SALARIO: salarios,
        }
    )
    com_ausentes = pd.concat(
        [
            base,
            pd.DataFrame(
                {
                    COLUNA_SALDO_MOVIMENTACAO: [SALDO_ADMISSAO] * extra_ausentes,
                    COLUNA_SECAO: ["A"] * extra_ausentes,
                    COLUNA_SALARIO: [float("nan")] * extra_ausentes,
                }
            ),
        ],
        ignore_index=True,
    )

    media_base = salario_medio_por_movimentacao(base)[COLUNA_SALARIO_MEDIO].iloc[0]
    media_com = salario_medio_por_movimentacao(com_ausentes)[COLUNA_SALARIO_MEDIO].iloc[0]

    assert math.isclose(media_base, media_com, rel_tol=1e-9, abs_tol=1e-6)

    # A média fica entre o menor e o maior salário válido.
    assert min(salarios) - 0.01 <= media_base <= max(salarios) + 0.01


# ---------------------------------------------------------------------------
# Property 17: Distribuição de escolaridade soma ao total (R4.7)
# ---------------------------------------------------------------------------


@st.composite
def _movimentacoes_escolaridade(draw: st.DrawFn) -> pd.DataFrame:
    """Gera movimentações com movimentação × seção × grau de instrução."""
    n = draw(st.integers(min_value=0, max_value=50))
    movs = draw(st.lists(_movimentacoes, min_size=n, max_size=n))
    secoes = draw(st.lists(_secoes, min_size=n, max_size=n))
    graus = draw(st.lists(_graus, min_size=n, max_size=n))
    return pd.DataFrame(
        {
            COLUNA_SALDO_MOVIMENTACAO: movs,
            COLUNA_SECAO: secoes,
            COLUNA_GRAU_INSTRUCAO: graus,
        }
    )


# Feature: datathon-caged-sc-pipeline, Property 17: Distribuição de escolaridade soma ao total
@given(df=_movimentacoes_escolaridade())
@settings(max_examples=100)
def test_prop17_distribuicao_escolaridade_soma_ao_total(
    df: pd.DataFrame,
) -> None:
    """Soma das contagens por grau = total do grupo; proporções somam 1.

    - Apenas admissões (+1) e desligamentos (-1) entram.
    - Para cada grupo (movimentação × seção), a soma das contagens por grau de
      instrução iguala o número de registros daquele grupo (ausentes incluídos
      como categoria própria), e as proporções do grupo somam 1 (R4.7).

    Validates: Requirements 4.7
    """
    resultado = distribuicao_escolaridade(df)

    assert list(resultado.columns) == [
        COLUNA_MOVIMENTACAO,
        COLUNA_SECAO,
        COLUNA_GRAU_INSTRUCAO,
        COLUNA_CONTAGEM,
        COLUNA_PROPORCAO,
    ]

    rotulos = {SALDO_ADMISSAO: MOVIMENTACAO_ADMISSAO, SALDO_DESLIGAMENTO: MOVIMENTACAO_DESLIGAMENTO}
    recorte = df[df[COLUNA_SALDO_MOVIMENTACAO].isin(rotulos)]

    if recorte.empty:
        assert resultado.empty
        return

    # Total esperado por grupo (movimentação × seção), independente do grau.
    totais_esperados: dict[tuple[str, str], int] = {}
    for mov, secao in zip(
        recorte[COLUNA_SALDO_MOVIMENTACAO], recorte[COLUNA_SECAO]
    ):
        chave = (rotulos[mov], secao)
        totais_esperados[chave] = totais_esperados.get(chave, 0) + 1

    # Agrupa o resultado por (movimentação, seção) e verifica somas.
    for (mov_rotulo, secao), bloco in resultado.groupby(
        [COLUNA_MOVIMENTACAO, COLUNA_SECAO], dropna=False
    ):
        total_grupo = totais_esperados[(mov_rotulo, secao)]

        # Soma das contagens iguala o total de registros do grupo (R4.7).
        assert int(bloco[COLUNA_CONTAGEM].sum()) == total_grupo

        # Proporções do grupo somam 1.
        assert math.isclose(
            float(bloco[COLUNA_PROPORCAO].sum()), 1.0, rel_tol=1e-9, abs_tol=1e-9
        )

        # Cada proporção é contagem/total do próprio grupo.
        for _, linha in bloco.iterrows():
            esperado = linha[COLUNA_CONTAGEM] / total_grupo
            assert math.isclose(
                float(linha[COLUNA_PROPORCAO]), esperado, rel_tol=1e-9, abs_tol=1e-12
            )

    # O conjunto de grupos reportados é exatamente o esperado.
    grupos_resultado = {
        (linha[COLUNA_MOVIMENTACAO], linha[COLUNA_SECAO])
        for _, linha in resultado.iterrows()
    }
    assert grupos_resultado == set(totais_esperados)


# Feature: datathon-caged-sc-pipeline, Property 17: Distribuição de escolaridade soma ao total
@given(
    n_adm=st.integers(min_value=0, max_value=30),
    n_desl=st.integers(min_value=0, max_value=30),
    graus=st.lists(_graus, min_size=1, max_size=5),
    data=st.data(),
)
@settings(max_examples=100)
def test_prop17_admitidos_e_desligados_contados_separadamente(
    n_adm: int, n_desl: int, graus: list, data: st.DataObject
) -> None:
    """Admitidos e desligados somam cada um ao seu próprio total (R4.7).

    Constrói um único setor "A" com ``n_adm`` admissões e ``n_desl``
    desligamentos, cada registro com um grau de instrução sorteado. A soma das
    contagens dos admitidos deve ser ``n_adm`` e a dos desligados ``n_desl``.

    Validates: Requirements 4.7
    """
    graus_adm = [data.draw(st.sampled_from(graus)) for _ in range(n_adm)]
    graus_desl = [data.draw(st.sampled_from(graus)) for _ in range(n_desl)]

    df = pd.DataFrame(
        {
            COLUNA_SALDO_MOVIMENTACAO: [SALDO_ADMISSAO] * n_adm
            + [SALDO_DESLIGAMENTO] * n_desl,
            COLUNA_SECAO: ["A"] * (n_adm + n_desl),
            COLUNA_GRAU_INSTRUCAO: graus_adm + graus_desl,
        }
    )

    resultado = distribuicao_escolaridade(df)

    soma_adm = int(
        resultado[resultado[COLUNA_MOVIMENTACAO] == MOVIMENTACAO_ADMISSAO][
            COLUNA_CONTAGEM
        ].sum()
    )
    soma_desl = int(
        resultado[resultado[COLUNA_MOVIMENTACAO] == MOVIMENTACAO_DESLIGAMENTO][
            COLUNA_CONTAGEM
        ].sum()
    )

    assert soma_adm == n_adm
    assert soma_desl == n_desl
