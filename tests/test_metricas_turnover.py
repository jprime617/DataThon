"""Teste de propriedade do Turnover do Calculador_de_Metricas (tarefa 7.4).

Valida, com Hypothesis (mín. 100 exemplos), a métrica de rotatividade de
`src/metricas.py`:

- Property 15: `Turnover` está sempre em [0, 1] ou é ausente (R4.4, R4.5). Para
  qualquer número de admissões e desligamentos, o `turnover` é igual a
  `min(admissões, desligamentos) / max(admissões, desligamentos)` quando o
  recorte tem ao menos uma movimentação, e é NaN quando não tem nenhuma.

O denominador é o maior dos dois contadores, e não um estoque de vínculos: o
CAGED movimentado não traz identificador de estabelecimento, então o estoque de
um recorte não é recuperável (ver a docstring de `metricas.turnover`). Como o
numerador é o menor dos dois e o denominador o maior, o resultado está em
[0, 1] **por construção** — não há clamp a testar, e sim a ausência dele.

LLM e Azure não entram aqui: a função sob teste é pura sobre DataFrames.
"""

from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.metricas import (
    COLUNA_CHAVE_MUNICIPAL,
    COLUNA_SALDO_MOVIMENTACAO,
    COLUNA_TURNOVER,
    turnover,
)

# ---------------------------------------------------------------------------
# Estratégias
# ---------------------------------------------------------------------------

# Recorte: poucos municípios/seções distintos para forçar agrupamentos reais.
_chaves_municipais = st.sampled_from(["420010", "420020", "420030", "420040"])
_secoes = st.sampled_from(["A", "B", "C"])

# Movimentação: majoritariamente +1/-1 (admissão/desligamento), mas também 0 e
# outros códigos, que não devem contar como admissão nem desligamento.
_movimentacoes = st.sampled_from([1, -1, 0, 2, -2])


@st.composite
def _movimentacoes_por_recorte(draw: st.DrawFn) -> pd.DataFrame:
    """Gera movimentações com recorte (município × seção).

    Pode gerar um DataFrame vazio, para exercitar o caso do conjunto vazio, e
    recortes só com admissões ou só com desligamentos, que devem dar turnover 0.
    """
    n = draw(st.integers(min_value=0, max_value=40))
    chaves = draw(st.lists(_chaves_municipais, min_size=n, max_size=n))
    secoes = draw(st.lists(_secoes, min_size=n, max_size=n))
    movs = draw(st.lists(_movimentacoes, min_size=n, max_size=n))
    return pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: chaves,
            "seção": secoes,
            COLUNA_SALDO_MOVIMENTACAO: movs,
        }
    )


# ---------------------------------------------------------------------------
# Property 15
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 15: Turnover está sempre em [0, 1] ou é ausente
@given(df=_movimentacoes_por_recorte())
@settings(max_examples=100)
def test_prop15_turnover_em_zero_um_ou_ausente(df: pd.DataFrame) -> None:
    """`min(adm, desl) / max(adm, desl)` ∈ [0, 1]; NaN sem movimentação.

    - Para cada recorte com ao menos uma admissão ou desligamento, o turnover é
      `min(admissões, desligamentos) / max(admissões, desligamentos)` (R4.4); em
      particular, nunca é menor que 0 nem maior que 1.
    - Para cada recorte sem admissão nem desligamento — só movimentações que não
      são +1 nem -1 —, o turnover é NaN (R4.5).
    - O DataFrame vazio não produz nenhum recorte.

    Validates: Requirements 4.4, 4.5
    """
    por = [COLUNA_CHAVE_MUNICIPAL, "seção"]
    resultado = turnover(df, por)

    if df.empty:
        assert resultado.empty
        assert list(resultado.columns) == [*por, COLUNA_TURNOVER]
        return

    admissoes: dict[tuple[str, str], int] = {}
    desligamentos: dict[tuple[str, str], int] = {}
    for chave, secao, mov in zip(
        df[COLUNA_CHAVE_MUNICIPAL], df["seção"], df[COLUNA_SALDO_MOVIMENTACAO]
    ):
        recorte = (chave, secao)
        admissoes[recorte] = admissoes.get(recorte, 0) + (1 if mov == 1 else 0)
        desligamentos[recorte] = desligamentos.get(recorte, 0) + (1 if mov == -1 else 0)

    recortes_resultado = {
        (linha[COLUNA_CHAVE_MUNICIPAL], linha["seção"])
        for _, linha in resultado.iterrows()
    }
    assert recortes_resultado == set(admissoes)

    for _, linha in resultado.iterrows():
        recorte = (linha[COLUNA_CHAVE_MUNICIPAL], linha["seção"])
        obtido = linha[COLUNA_TURNOVER]
        adm, desl = admissoes[recorte], desligamentos[recorte]

        if max(adm, desl) == 0:
            # Recorte sem admissão nem desligamento → rotatividade indefinida.
            assert math.isnan(obtido)
        else:
            assert 0.0 <= obtido <= 1.0
            assert math.isclose(
                obtido, min(adm, desl) / max(adm, desl), rel_tol=1e-9, abs_tol=1e-12
            )


# Feature: datathon-caged-sc-pipeline, Property 15: Turnover está sempre em [0, 1] ou é ausente
@given(
    admissoes=st.integers(min_value=0, max_value=500),
    desligamentos=st.integers(min_value=0, max_value=500),
)
@settings(max_examples=100)
def test_prop15_fluxo_equilibrado_da_um_e_fluxo_unilateral_da_zero(
    admissoes: int, desligamentos: int
) -> None:
    """Os dois extremos da escala têm leitura de negócio direta (R4.4).

    - Admissões e desligamentos iguais e não nulos → ``1``: rotatividade pura,
      saldo nulo, que é a assinatura do apagão de mão de obra.
    - Só admissões ou só desligamentos → ``0``: crescimento ou encolhimento
      puro, sem rotatividade.

    Validates: Requirements 4.4, 4.5
    """
    movs = [1] * admissoes + [-1] * desligamentos
    df = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["420010"] * len(movs),
            "seção": ["C"] * len(movs),
            COLUNA_SALDO_MOVIMENTACAO: movs,
        }
    )
    resultado = turnover(df, [COLUNA_CHAVE_MUNICIPAL, "seção"])

    if not movs:
        assert resultado.empty
        return

    valor = resultado[COLUNA_TURNOVER].iloc[0]
    assert 0.0 <= valor <= 1.0
    if admissoes == desligamentos:
        assert valor == 1.0
    elif min(admissoes, desligamentos) == 0:
        assert valor == 0.0


def test_turnover_sem_movimentacao_valida_e_ausente() -> None:
    """Recorte só com códigos que não são +1 nem -1 tem turnover ausente (R4.5)."""
    df = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["420010", "420010"],
            "seção": ["C", "C"],
            COLUNA_SALDO_MOVIMENTACAO: [0, 2],
        }
    )
    resultado = turnover(df, [COLUNA_CHAVE_MUNICIPAL, "seção"])
    assert math.isnan(resultado[COLUNA_TURNOVER].iloc[0])
