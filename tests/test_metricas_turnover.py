"""Teste de propriedade do Turnover do Calculador_de_Metricas (tarefa 7.4).

Valida, com Hypothesis (mín. 100 exemplos), a métrica de rotatividade de
`src/metricas.py`:

- Property 15: `Turnover` está sempre em [0, 1] ou é ausente (R4.4, R4.5). Para
  qualquer número de admissões, desligamentos e estoque base, o `turnover` é
  igual a `min(admissões, desligamentos) / estoque_base` limitado ao intervalo
  [0, 1] quando o estoque base é um número maior que zero, e é NaN quando o
  estoque base é zero, ausente ou não numérico (rótulo de faixa sem número).

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
    COLUNA_ESTOQUE_BASE,
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

# Estoque base (`estoque_base`), em formas heterogêneas que o Limpador pode
# produzir, para exercitar a coerção robusta do denominador:
# - inteiro/float positivo → fórmula aplicável;
# - zero/negativo → ausente (R4.5);
# - None/NaN → ausente (R4.5);
# - texto numérico (inclusive formato BR) → coagido para número;
# - rótulo de faixa sem número → ausente (R4.5).
_estoques = st.one_of(
    st.integers(min_value=1, max_value=5_000),
    st.floats(min_value=1.0, max_value=5_000.0, allow_nan=False, allow_infinity=False),
    st.just(0),
    st.just(0.0),
    st.integers(min_value=-5_000, max_value=-1),
    st.none(),
    st.just(float("nan")),
    st.sampled_from(["120", "1.234,0", "Até 4", "De 5 a 9", "", "n/d"]),
)


@st.composite
def _movimentacoes_com_estoque(draw: st.DrawFn) -> pd.DataFrame:
    """Gera movimentações com recorte (município × seção) e estoque base.

    O estoque base é sorteado **por recorte** (característica do estabelecimento,
    não do fluxo) e repetido em todas as linhas daquele recorte, replicando a
    semântica de `turnover` (primeiro valor observado no grupo). Pode gerar um
    DataFrame vazio, para exercitar o caso do conjunto vazio.
    """
    n = draw(st.integers(min_value=0, max_value=40))
    chaves = draw(st.lists(_chaves_municipais, min_size=n, max_size=n))
    secoes = draw(st.lists(_secoes, min_size=n, max_size=n))
    movs = draw(st.lists(_movimentacoes, min_size=n, max_size=n))

    # Estoque base consistente por recorte (município × seção).
    estoque_por_recorte: dict[tuple[str, str], object] = {}
    estoques: list[object] = []
    for chave, secao in zip(chaves, secoes):
        recorte = (chave, secao)
        if recorte not in estoque_por_recorte:
            estoque_por_recorte[recorte] = draw(_estoques)
        estoques.append(estoque_por_recorte[recorte])

    return pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: chaves,
            "seção": secoes,
            COLUNA_SALDO_MOVIMENTACAO: movs,
            COLUNA_ESTOQUE_BASE: estoques,
        }
    )


def _estoque_positivo(valor: object) -> float | None:
    """Coage o estoque como `turnover` faz; retorna o número se > 0, senão None.

    Replica a tolerância de `turnover` a inteiros, floats, texto numérico (BR)
    e rótulos de faixa, de forma independente da implementação, para decidir se
    o recorte deve ter turnover numérico (estoque > 0) ou NaN.
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        num = float(valor)
    else:
        texto = str(valor).strip()
        if not texto:
            return None
        try:
            num = float(texto)
        except ValueError:
            try:
                num = float(texto.replace(".", "").replace(",", "."))
            except ValueError:
                return None
    if math.isnan(num) or num <= 0:
        return None
    return num


# ---------------------------------------------------------------------------
# Property 15
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 15: Turnover está sempre em [0, 1] ou é ausente
@given(df=_movimentacoes_com_estoque())
@settings(max_examples=100)
def test_prop15_turnover_em_zero_um_ou_ausente(df: pd.DataFrame) -> None:
    """`min(adm, desl) / estoque_base` ∈ [0, 1] se estoque > 0; senão NaN.

    - Para cada recorte com estoque base numérico maior que zero, o turnover é
      `min(admissões, desligamentos) / estoque` limitado ao intervalo [0, 1]
      (R4.4); em particular, nunca é menor que 0 nem maior que 1.
    - Para cada recorte cujo estoque base é zero, ausente ou não numérico, o
      turnover é NaN (R4.5).
    - O DataFrame vazio não produz nenhum recorte.

    Validates: Requirements 4.4, 4.5
    """
    por = [COLUNA_CHAVE_MUNICIPAL, "seção"]
    resultado = turnover(df, por)

    if df.empty:
        assert resultado.empty
        assert list(resultado.columns) == [*por, COLUNA_TURNOVER]
        return

    # Balanço esperado por recorte: nº de admissões, desligamentos e estoque.
    admissoes: dict[tuple[str, str], int] = {}
    desligamentos: dict[tuple[str, str], int] = {}
    estoque_recorte: dict[tuple[str, str], object] = {}
    for chave, secao, mov, est in zip(
        df[COLUNA_CHAVE_MUNICIPAL],
        df["seção"],
        df[COLUNA_SALDO_MOVIMENTACAO],
        df[COLUNA_ESTOQUE_BASE],
    ):
        recorte = (chave, secao)
        admissoes[recorte] = admissoes.get(recorte, 0) + (1 if mov == 1 else 0)
        desligamentos[recorte] = desligamentos.get(recorte, 0) + (1 if mov == -1 else 0)
        # Estoque é constante por recorte (gerador garante), basta o primeiro.
        estoque_recorte.setdefault(recorte, est)

    # Mesmos recortes nos dois lados.
    recortes_resultado = {
        (linha[COLUNA_CHAVE_MUNICIPAL], linha["seção"])
        for _, linha in resultado.iterrows()
    }
    assert recortes_resultado == set(estoque_recorte)

    for _, linha in resultado.iterrows():
        recorte = (linha[COLUNA_CHAVE_MUNICIPAL], linha["seção"])
        obtido = linha[COLUNA_TURNOVER]
        estoque = _estoque_positivo(estoque_recorte[recorte])

        if estoque is None:
            # Estoque zero, ausente ou não numérico → turnover ausente (R4.5).
            assert math.isnan(obtido)
        else:
            esperado_bruto = min(admissoes[recorte], desligamentos[recorte]) / estoque
            esperado = min(max(esperado_bruto, 0.0), 1.0)
            # Sempre dentro de [0, 1] (R4.4).
            assert 0.0 <= obtido <= 1.0
            assert math.isclose(obtido, esperado, rel_tol=1e-9, abs_tol=1e-12)


# Feature: datathon-caged-sc-pipeline, Property 15: Turnover está sempre em [0, 1] ou é ausente
@given(
    admissoes=st.integers(min_value=0, max_value=500),
    desligamentos=st.integers(min_value=0, max_value=500),
    estoque=st.integers(min_value=1, max_value=1_000),
)
@settings(max_examples=100)
def test_prop15_fluxo_acima_do_estoque_satura_em_um(
    admissoes: int, desligamentos: int, estoque: int
) -> None:
    """Fluxo maior que o estoque base satura o turnover em 1 (R4.4).

    Monta um único recorte com ``admissoes`` admissões e ``desligamentos``
    desligamentos sobre um estoque positivo; o resultado nunca ultrapassa 1,
    mesmo quando `min(adm, desl)` excede o estoque.

    Validates: Requirements 4.4, 4.5
    """
    movs = [1] * admissoes + [-1] * desligamentos
    # Garante ao menos uma linha para o recorte existir (código vazio → 0 linhas).
    if not movs:
        movs = [0]
    df = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["420010"] * len(movs),
            COLUNA_SALDO_MOVIMENTACAO: movs,
            COLUNA_ESTOQUE_BASE: [estoque] * len(movs),
        }
    )

    resultado = turnover(df, [COLUNA_CHAVE_MUNICIPAL])

    assert len(resultado) == 1
    obtido = resultado[COLUNA_TURNOVER].iloc[0]
    esperado = min(min(admissoes, desligamentos) / estoque, 1.0)
    assert 0.0 <= obtido <= 1.0
    assert math.isclose(obtido, esperado, rel_tol=1e-9, abs_tol=1e-12)


# Feature: datathon-caged-sc-pipeline, Property 15: Turnover está sempre em [0, 1] ou é ausente
@given(
    admissoes=st.integers(min_value=0, max_value=200),
    desligamentos=st.integers(min_value=0, max_value=200),
    estoque=st.sampled_from([0, 0.0, -1, -100, None, float("nan"), "", "Até 4"]),
)
@settings(max_examples=100)
def test_prop15_estoque_invalido_resulta_em_nan(
    admissoes: int, desligamentos: int, estoque: object
) -> None:
    """Estoque zero/negativo/ausente/não numérico → turnover NaN (R4.5).

    Independentemente do fluxo de admissões e desligamentos, um estoque base
    que não é um número positivo torna o turnover ausente.

    Validates: Requirements 4.4, 4.5
    """
    movs = [1] * admissoes + [-1] * desligamentos
    # Garante ao menos uma linha para o recorte existir.
    if not movs:
        movs = [0]
    df = pd.DataFrame(
        {
            COLUNA_CHAVE_MUNICIPAL: ["420010"] * len(movs),
            COLUNA_SALDO_MOVIMENTACAO: movs,
            COLUNA_ESTOQUE_BASE: [estoque] * len(movs),
        }
    )

    resultado = turnover(df, [COLUNA_CHAVE_MUNICIPAL])

    assert len(resultado) == 1
    assert math.isnan(resultado[COLUNA_TURNOVER].iloc[0])
