"""Testes de propriedade do Ingestor (tarefa 3.4).

Implementam as propriedades 1–4 do design com Hypothesis (mín. 100 exemplos,
perfil `datathon` carregado em `conftest.py`), com tag de rastreabilidade
obrigatória por propriedade:

- Property 1: Validação de UF detecta e conta divergentes — R1.4, R1.5
- Property 2: Validação de colunas identifica exatamente as ausentes — R1.6, R1.7
- Property 3: Contagem de linhas lida é exata — R1.9
- Property 4: Round-trip de persistência Parquet — R1.3, R1.8

As propriedades 1 e 2 exercem funções puras de validação. As propriedades 3 e 4
geram pequenos DataFrames CAGED-like, escrevem-nos em CSV num diretório temporário
e os processam por `executar_ingestao`, verificando a contagem exata de linhas
lidas (P3) e o round-trip do Parquet bruto sem colunas `Unnamed:*` (P4).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.erros import ErroDeValidacao
from src.ingestao import (
    COLUNAS_OBRIGATORIAS_CAGED,
    UF_ESPERADA,
    executar_ingestao,
    ler_caged,
    validar_colunas,
    validar_uf,
)

# ---------------------------------------------------------------------------
# Estratégias auxiliares.
# ---------------------------------------------------------------------------

# UFs divergentes: qualquer inteiro de UF brasileira diferente de 42.
_UF_DIVERGENTE = st.integers(min_value=11, max_value=53).filter(
    lambda v: v != UF_ESPERADA
)


def _linhas_uf(n_validas: int, divergentes: list[int]) -> pd.DataFrame:
    """Monta um DataFrame com `n_validas` linhas uf==42 e as `divergentes`."""
    valores = [UF_ESPERADA] * n_validas + list(divergentes)
    return pd.DataFrame({"uf": valores})


@st.composite
def _caged_df(draw) -> pd.DataFrame:
    """Gera um DataFrame CAGED-like pequeno e válido para ingestão.

    - entre 0 e 15 linhas de dados;
    - todas as colunas obrigatórias presentes (R1.6) e `uf == 42` (R1.4);
    - valores simples (texto), coerentes com a leitura `dtype=str`.
    """
    n = draw(st.integers(min_value=0, max_value=15))
    dados: dict[str, list] = {}
    for col in COLUNAS_OBRIGATORIAS_CAGED:
        dados[col] = [
            draw(st.integers(min_value=0, max_value=9_999)) for _ in range(n)
        ]
    dados["uf"] = [UF_ESPERADA] * n
    return pd.DataFrame(dados)


def _escrever_caged_csv(df: pd.DataFrame, caminho: Path) -> None:
    """Grava um DataFrame CAGED-like no formato de origem (sep=';', dec=',')."""
    df.to_csv(caminho, sep=";", decimal=",", index=False, encoding="utf-8")


def _municipios_csv(caminho: Path, n: int) -> None:
    """Gera um CSV de municípios mínimo (sep=',') com `n` linhas de dados."""
    linhas = ["Município,Código,População estimada - pessoas [2026]"]
    for i in range(n):
        linhas.append(f"Municipio {i},4200{i:03d},{1000 + i}")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Property 1: Validação de UF detecta e conta divergentes.
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 1: Validação de UF detecta e conta divergentes
@settings(max_examples=100)
@given(
    n_validas=st.integers(min_value=0, max_value=50),
    divergentes=st.lists(_UF_DIVERGENTE, min_size=0, max_size=20),
)
def test_prop1_validacao_uf_detecta_e_conta_divergentes(n_validas, divergentes):
    # Feature: datathon-caged-sc-pipeline, Property 1: Validação de UF detecta e conta divergentes
    # Validates: Requirements 1.4, 1.5
    df = _linhas_uf(n_validas, divergentes)
    n_divergentes = len(divergentes)

    if n_divergentes == 0:
        # Aprova sse todas as linhas têm uf == 42.
        assert validar_uf(df) is None
    else:
        # Falha e reporta exatamente a quantidade de linhas uf != 42.
        try:
            validar_uf(df)
        except ErroDeValidacao as exc:
            assert str(n_divergentes) in str(exc)
        else:
            raise AssertionError("esperava ErroDeValidacao para uf divergente")


# ---------------------------------------------------------------------------
# Property 2: Validação de colunas identifica exatamente as ausentes.
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 2: Validação de colunas identifica exatamente as ausentes
@settings(max_examples=100)
@given(
    indices_remover=st.lists(
        st.integers(min_value=0, max_value=len(COLUNAS_OBRIGATORIAS_CAGED) - 1),
        min_size=0,
        max_size=len(COLUNAS_OBRIGATORIAS_CAGED),
        unique=True,
    )
)
def test_prop2_validacao_colunas_identifica_exatamente_as_ausentes(indices_remover):
    # Feature: datathon-caged-sc-pipeline, Property 2: Validação de colunas identifica exatamente as ausentes
    # Validates: Requirements 1.6, 1.7
    removidas = [COLUNAS_OBRIGATORIAS_CAGED[i] for i in indices_remover]
    restantes = [c for c in COLUNAS_OBRIGATORIAS_CAGED if c not in removidas]

    df = pd.DataFrame({col: [1, 2] for col in restantes})

    if not removidas:
        # Aprova sse nenhuma coluna obrigatória falta.
        assert validar_colunas(df) is None
    else:
        # Falha listando exatamente o conjunto de colunas ausentes.
        try:
            validar_colunas(df)
        except ErroDeValidacao as exc:
            mensagem = str(exc)
            # Compara pela forma `repr(col)` ('nome') usada pela implementação,
            # evitando falsos positivos entre nomes que são substring um do outro
            # (ex.: 'salário' ⊂ 'valorsaláriofixo').
            for col in removidas:
                assert repr(col) in mensagem
            # Nenhuma coluna presente é indevidamente reportada como ausente.
            for col in restantes:
                assert repr(col) not in mensagem
        else:
            raise AssertionError("esperava ErroDeValidacao para colunas ausentes")


# ---------------------------------------------------------------------------
# Property 3: Contagem de linhas lida é exata.
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 3: Contagem de linhas lida é exata
@settings(max_examples=100)
@given(df_caged=_caged_df(), n_municipios=st.integers(min_value=0, max_value=20))
def test_prop3_contagem_de_linhas_lida_e_exata(df_caged, n_municipios, tmp_path_factory):
    # Feature: datathon-caged-sc-pipeline, Property 3: Contagem de linhas lida é exata
    # Validates: Requirements 1.9
    base = tmp_path_factory.mktemp("prop3")
    caminho_caged = base / "caged.csv"
    caminho_municipios = base / "municipios.csv"
    destino = base / "caged_bruto.parquet"

    _escrever_caged_csv(df_caged, caminho_caged)
    _municipios_csv(caminho_municipios, n_municipios)

    resultado = executar_ingestao(
        str(caminho_caged), str(caminho_municipios), str(destino)
    )

    # A contagem registrada é igual ao número de linhas de dados de cada arquivo.
    assert resultado.linhas_caged == len(df_caged)
    assert resultado.linhas_municipios == n_municipios


# ---------------------------------------------------------------------------
# Property 4: Round-trip de persistência Parquet.
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 4: Round-trip de persistência Parquet
@settings(max_examples=100)
@given(
    df_caged=_caged_df(),
    n_unnamed=st.integers(min_value=0, max_value=2),
)
def test_prop4_round_trip_persistencia_parquet(df_caged, n_unnamed, tmp_path_factory):
    # Feature: datathon-caged-sc-pipeline, Property 4: Round-trip de persistência Parquet
    # Validates: Requirements 1.3, 1.8
    base = tmp_path_factory.mktemp("prop4")
    caminho_caged = base / "caged.csv"
    caminho_municipios = base / "municipios.csv"
    destino = base / "caged_bruto.parquet"

    # Injeta colunas de índice espúrias que devem desaparecer no round-trip (R1.3).
    df_origem = df_caged.copy()
    colunas_unnamed = ["Unnamed: 0", "Unnamed: 0.1"][:n_unnamed]
    for pos, col in enumerate(colunas_unnamed):
        df_origem.insert(pos, col, range(len(df_origem)))

    _escrever_caged_csv(df_origem, caminho_caged)
    _municipios_csv(caminho_municipios, 1)

    executar_ingestao(str(caminho_caged), str(caminho_municipios), str(destino))

    # O Parquet foi persistido (R1.8) e pode ser relido.
    assert destino.exists()
    relido = pd.read_parquet(destino)

    # Referência: o que `ler_caged` produz a partir do mesmo CSV — já sem Unnamed:*.
    esperado = ler_caged(str(caminho_caged))

    # Nenhuma coluna Unnamed:* sobrevive ao round-trip (R1.3).
    assert not any(str(c).startswith("Unnamed") for c in relido.columns)
    # Mesmas colunas e mesmos dados (comparados como texto, pois a leitura usa str).
    assert list(relido.columns) == list(esperado.columns)
    pd.testing.assert_frame_equal(
        relido.astype(str).reset_index(drop=True),
        esperado.astype(str).reset_index(drop=True),
    )
