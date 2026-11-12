"""Testes de exportação do Agregador (tarefa 10.4).

Valida a função `exportar(df_agregado, destino)` de `src/agregador.py`, que grava
a tabela agregada em Parquet ou CSV (formato escolhido pela extensão de
`destino`), com gravação atômica via arquivo temporário + `os.replace` (R6.3) e
falha explícita sem deixar arquivo parcial (R6.4):

- Property 24: Round-trip de exportação do agregado — para qualquer tabela
  agregada, exportá-la (Parquet ou CSV) e relê-la preserva os dados (R6.3).
- Teste de exemplo: uma exportação que falha (extensão não suportada, destino
  inválido) levanta `ErroDeValidacao`, registra o `destino` no log de erro e não
  deixa arquivo parcial — nem o destino final, nem resíduo `.tmp` (R6.4).

As funções sob teste são puras sobre DataFrames + sistema de arquivos; LLM e
Azure não entram aqui.
"""

from __future__ import annotations

import logging
import math
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agregador import (
    COLUNA_IDHM_2010,
    COLUNA_MACROFAMILIA_CBO,
    COLUNA_MES,
    COLUNA_MUNICIPIO,
    COLUNA_PIB_PER_CAPITA_2023,
    COLUNA_POPULACAO_2026,
    COLUNA_REGIAO,
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_POR_10K,
    COLUNA_SECAO_INDUSTRIAL,
    EXTENSAO_CSV,
    EXTENSAO_PARQUET,
    exportar,
)
from src.erros import ErroDeValidacao
from src.logging_pipeline import obter_logger

# ---------------------------------------------------------------------------
# Estratégias: tabelas agregadas no schema de saída de `agregar` (R6)
# ---------------------------------------------------------------------------

# Chaves municipais (regiao == municipio no schema, ambos a chave de 6 dígitos).
_chaves = st.sampled_from(["420010", "420020", "420030", "420040"])
_secoes = st.sampled_from(["A", "B", "C"])
_macrofamilias = st.sampled_from(["Indústria", "Serviços", "Não classificado"])
_meses = st.sampled_from([202509, 202510, 202511, 202512])

# Métricas: float com 2 casas (R6.5) ou NaN (município sem população, etc.).
_metricas = st.one_of(
    st.just(math.nan),
    st.integers(min_value=-100_000, max_value=100_000).map(lambda v: v / 100.0),
)

# Indicadores municipais: inteiros/floats ou NaN (indicador ausente — R6.7).
_populacao = st.one_of(st.just(math.nan), st.integers(1, 2_000_000).map(float))
_idhm = st.one_of(st.just(math.nan), st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False))
_pib = st.one_of(st.just(math.nan), st.floats(0.0, 500_000.0, allow_nan=False, allow_infinity=False))


@st.composite
def _agregado(draw: st.DrawFn) -> pd.DataFrame:
    """Gera uma tabela agregada no schema de saída de `agregar` (R6).

    As colunas e dtypes reproduzem o que `agregar` produz: recorte textual/int,
    quatro métricas float64 (possivelmente NaN) e três indicadores float64
    (possivelmente NaN). Pode ser vazia, para exercitar o round-trip trivial.
    """
    n = draw(st.integers(min_value=0, max_value=25))
    colunas = {
        COLUNA_REGIAO: draw(st.lists(_chaves, min_size=n, max_size=n)),
        COLUNA_MUNICIPIO: None,  # preenchido abaixo igual a regiao
        COLUNA_SECAO_INDUSTRIAL: draw(st.lists(_secoes, min_size=n, max_size=n)),
        COLUNA_MACROFAMILIA_CBO: draw(st.lists(_macrofamilias, min_size=n, max_size=n)),
        COLUNA_MES: draw(st.lists(_meses, min_size=n, max_size=n)),
        COLUNA_SALDO_LIQUIDO: draw(st.lists(_metricas, min_size=n, max_size=n)),
        COLUNA_SALDO_POR_10K: draw(st.lists(_metricas, min_size=n, max_size=n)),
        COLUNA_POPULACAO_2026: draw(st.lists(_populacao, min_size=n, max_size=n)),
        COLUNA_IDHM_2010: draw(st.lists(_idhm, min_size=n, max_size=n)),
        COLUNA_PIB_PER_CAPITA_2023: draw(st.lists(_pib, min_size=n, max_size=n)),
    }
    colunas[COLUNA_MUNICIPIO] = list(colunas[COLUNA_REGIAO])
    df = pd.DataFrame(colunas)
    # Dtypes como na saída de `agregar`: métricas e indicadores em float64.
    for coluna in (
        COLUNA_SALDO_LIQUIDO,
        COLUNA_SALDO_POR_10K,
        COLUNA_POPULACAO_2026,
        COLUNA_IDHM_2010,
        COLUNA_PIB_PER_CAPITA_2023,
    ):
        df[coluna] = df[coluna].astype("float64")
    df[COLUNA_MES] = df[COLUNA_MES].astype("int64")
    return df


def _reler(destino: Path) -> pd.DataFrame:
    """Relê um arquivo exportado escolhendo o leitor pela extensão."""
    if destino.suffix.lower() == EXTENSAO_PARQUET:
        return pd.read_parquet(destino)
    return pd.read_csv(destino)


# ---------------------------------------------------------------------------
# Property 24: Round-trip de exportação do agregado
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 24: Round-trip de exportação do agregado
@given(df=_agregado(), extensao=st.sampled_from([EXTENSAO_PARQUET, EXTENSAO_CSV]))
@settings(max_examples=100)
def test_prop24_round_trip_de_exportacao_do_agregado(
    df: pd.DataFrame, extensao: str
) -> None:
    """Exportar a tabela agregada e relê-la recupera os mesmos dados (R6.3).

    Para qualquer tabela agregada e qualquer formato suportado (Parquet ou CSV),
    `exportar` grava o arquivo e relê-lo reproduz as mesmas colunas e valores —
    textos exatos, meses inteiros e métricas/indicadores float (NaN preservado).

    Cada exemplo usa um diretório temporário próprio (via `tempfile`) para ser
    compatível com Hypothesis, que não aceita a fixture `tmp_path`.

    Validates: Requirements 6.3
    """
    with tempfile.TemporaryDirectory() as pasta:
        destino = Path(pasta) / f"caged_agregado{extensao}"

        exportar(df, destino)

        assert destino.exists()
        relido = _reler(destino)

        # Mesmas colunas, na mesma ordem.
        assert list(relido.columns) == list(df.columns)
        assert len(relido) == len(df)

        if df.empty:
            return

        # Recortes textuais e mês preservados exatamente.
        for coluna in (
            COLUNA_REGIAO,
            COLUNA_MUNICIPIO,
            COLUNA_SECAO_INDUSTRIAL,
            COLUNA_MACROFAMILIA_CBO,
        ):
            assert list(relido[coluna].astype(str)) == list(df[coluna].astype(str))
        assert list(relido[COLUNA_MES].astype("int64")) == list(df[COLUNA_MES])

        # Métricas e indicadores float preservados, inclusive NaN.
        for coluna in (
            COLUNA_SALDO_LIQUIDO,
            COLUNA_SALDO_POR_10K,
            COLUNA_POPULACAO_2026,
            COLUNA_IDHM_2010,
            COLUNA_PIB_PER_CAPITA_2023,
        ):
            esperado = df[coluna].astype("float64").tolist()
            obtido = relido[coluna].astype("float64").tolist()
            assert len(esperado) == len(obtido)
            for e, o in zip(esperado, obtido):
                if math.isnan(e):
                    assert math.isnan(o)
                else:
                    assert o == pytest.approx(e)


# ---------------------------------------------------------------------------
# Teste de exemplo: falha de exportação (R6.4)
# ---------------------------------------------------------------------------


def _agregado_minimo() -> pd.DataFrame:
    """Uma tabela agregada mínima, não-vazia, no schema de saída (R6)."""
    return pd.DataFrame(
        {
            COLUNA_REGIAO: ["420010"],
            COLUNA_MUNICIPIO: ["420010"],
            COLUNA_SECAO_INDUSTRIAL: ["C"],
            COLUNA_MACROFAMILIA_CBO: ["Indústria"],
            COLUNA_MES: [202509],
            COLUNA_SALDO_LIQUIDO: [1.0],
            COLUNA_SALDO_POR_10K: [0.5],
            COLUNA_POPULACAO_2026: [12345.0],
            COLUNA_IDHM_2010: [0.8],
            COLUNA_PIB_PER_CAPITA_2023: [42000.0],
        }
    )


def test_exportacao_extensao_nao_suportada_registra_destino_sem_arquivo_parcial(
    tmp_path, caplog
) -> None:
    """Extensão não suportada: erro com destino no log e sem arquivo parcial.

    Exportar para um destino com extensão fora de {.parquet, .csv} deve levantar
    `ErroDeValidacao`, registrar uma mensagem de erro que identifica o destino e
    não deixar nenhum arquivo gravado — nem o destino, nem resíduo `.tmp` (R6.4).

    Requirements: 6.4
    """
    df = _agregado_minimo()
    destino = tmp_path / "caged_agregado.txt"
    logger = obter_logger()

    with caplog.at_level(logging.ERROR, logger=logger.name):
        with pytest.raises(ErroDeValidacao) as excecao:
            exportar(df, destino)

    # O erro identifica o destino (R6.4).
    assert str(destino) in str(excecao.value)

    erros = [r for r in caplog.records if r.name == logger.name and r.levelno == logging.ERROR]
    assert len(erros) == 1
    assert str(destino) in erros[0].getMessage()

    # Nenhum arquivo parcial: nem o destino final, nem o temporário.
    assert not destino.exists()
    assert not (tmp_path / f"{destino.name}.tmp").exists()
    assert list(tmp_path.iterdir()) == []


def test_exportacao_destino_invalido_registra_destino_sem_arquivo_parcial(
    tmp_path, caplog
) -> None:
    """Destino inválido (diretório inexistente): erro com destino, sem parcial.

    Gravar num diretório que não existe falha na serialização. A exportação deve
    levantar `ErroDeValidacao`, registrar o destino no log de erro e não deixar
    arquivo parcial nem resíduo `.tmp` (R6.4).

    Requirements: 6.4
    """
    df = _agregado_minimo()
    # Subdiretório inexistente -> a gravação do temporário falha.
    destino = tmp_path / "inexistente" / "caged_agregado.parquet"
    logger = obter_logger()

    with caplog.at_level(logging.ERROR, logger=logger.name):
        with pytest.raises(ErroDeValidacao) as excecao:
            exportar(df, destino)

    assert str(destino) in str(excecao.value)

    erros = [r for r in caplog.records if r.name == logger.name and r.levelno == logging.ERROR]
    assert len(erros) == 1
    assert str(destino) in erros[0].getMessage()

    # O diretório inexistente continua inexistente: nada foi criado/parcial.
    assert not destino.exists()
    assert not destino.parent.exists()


def test_exportacao_falha_preserva_destino_anterior_integro(tmp_path) -> None:
    """Falha numa nova exportação preserva um destino íntegro já existente (R6.4).

    Se o destino já continha uma exportação válida e uma nova chamada falha (por
    serialização), o arquivo anterior deve permanecer intacto e legível, e nenhum
    `.tmp` deve sobrar.

    Requirements: 6.4
    """
    destino = tmp_path / "caged_agregado.parquet"

    # Primeira exportação bem-sucedida.
    bom = _agregado_minimo()
    exportar(bom, destino)
    assert destino.exists()

    # Segunda exportação falha: tipo não serializável em Parquet força exceção.
    ruim = _agregado_minimo()
    ruim[COLUNA_SALDO_LIQUIDO] = [object()]
    with pytest.raises(ErroDeValidacao):
        exportar(ruim, destino)

    # Destino anterior permanece íntegro e sem resíduo .tmp.
    assert destino.exists()
    assert not (tmp_path / f"{destino.name}.tmp").exists()
    relido = pd.read_parquet(destino)
    assert len(relido) == len(bom)
    assert list(relido.columns) == list(bom.columns)
