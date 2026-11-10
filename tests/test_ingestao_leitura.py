"""Testes de exemplo da leitura de arquivos do Ingestor (tarefa 3.5).

Cobrem os critérios de aceitação de leitura e de erro de I/O:
- R1.1: CAGED lido com separador ';' e decimal ','.
- R1.2: Base_de_Municipios lida com separador ','.
- R1.3: colunas de índice `Unnamed: 0.1` e `Unnamed: 0` descartadas do CAGED.
- R1.10: arquivo ausente/inacessível/ilegível levanta erro que identifica o arquivo.

Usam fixtures pequenos escritos em `tmp_path`, de modo que nenhum artefato
temporário persista após a execução (o pytest limpa `tmp_path` automaticamente).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.erros import ErroDeValidacao
from src.ingestao import ler_caged, ler_municipios

# ---------------------------------------------------------------------------
# Fixtures de conteúdo mínimo das duas fontes.
# ---------------------------------------------------------------------------

# CAGED: separador ';', decimal ',', com as duas colunas de índice espúrias que
# devem ser descartadas (R1.3). Duas linhas de dados.
_CAGED_CSV = (
    "Unnamed: 0;Unnamed: 0.1;competênciamov;município;saldomovimentação;salário\n"
    "0;0;202509;420890;1;2018,00\n"
    "1;1;202510;421660;-1;1500,50\n"
)

# Municípios: separador ','. Dois municípios.
_MUNICIPIOS_CSV = (
    "Município,Código,População estimada - pessoas [2026]\n"
    "Abdon Batista,4200051,2650\n"
    "Abelardo Luz,4200101,18100\n"
)


@pytest.fixture
def arquivo_caged(tmp_path: Path) -> str:
    caminho = tmp_path / "caged_fixture.csv"
    caminho.write_text(_CAGED_CSV, encoding="utf-8")
    return str(caminho)


@pytest.fixture
def arquivo_municipios(tmp_path: Path) -> str:
    caminho = tmp_path / "municipios_fixture.csv"
    caminho.write_text(_MUNICIPIOS_CSV, encoding="utf-8")
    return str(caminho)


# ---------------------------------------------------------------------------
# Leitura bem-sucedida.
# ---------------------------------------------------------------------------


def test_ler_caged_usa_separador_e_decimal_corretos(arquivo_caged):
    # R1.1: ao usar sep=';' e decimal=',', as colunas são separadas por ';' e
    # o valor monetário BR é lido como texto único (a conversão numérica fica
    # na etapa de limpeza). Se o separador estivesse errado, haveria 1 coluna só.
    df = ler_caged(arquivo_caged)

    assert len(df) == 2
    assert "competênciamov" in df.columns
    assert "saldomovimentação" in df.columns
    # Com sep=';' a coluna de salário fica isolada e preserva a vírgula decimal.
    assert df.loc[0, "salário"] == "2018,00"
    assert df.loc[0, "competênciamov"] == "202509"


def test_ler_caged_descarta_colunas_unnamed(arquivo_caged):
    # R1.3: colunas de índice 'Unnamed: 0' e 'Unnamed: 0.1' não devem sobreviver.
    df = ler_caged(arquivo_caged)

    assert "Unnamed: 0" not in df.columns
    assert "Unnamed: 0.1" not in df.columns
    assert not any(str(c).startswith("Unnamed") for c in df.columns)


def test_ler_caged_sem_colunas_unnamed_nao_quebra(tmp_path: Path):
    # A remoção de colunas é condicional: um CAGED sem as colunas de índice
    # deve ser lido normalmente (R1.3 não deve falhar quando não há o que remover).
    conteudo = (
        "competênciamov;município;saldomovimentação;salário\n"
        "202509;420890;1;2018,00\n"
    )
    caminho = tmp_path / "caged_sem_indice.csv"
    caminho.write_text(conteudo, encoding="utf-8")

    df = ler_caged(str(caminho))

    assert list(df.columns) == [
        "competênciamov",
        "município",
        "saldomovimentação",
        "salário",
    ]
    assert len(df) == 1


def test_ler_municipios_usa_separador_virgula(arquivo_municipios):
    # R1.2: separador ',' separa as três colunas da base de municípios.
    df = ler_municipios(arquivo_municipios)

    assert len(df) == 2
    assert "Código" in df.columns
    assert "Município" in df.columns
    assert df.loc[0, "Código"] == "4200051"
    assert df.loc[1, "Município"] == "Abelardo Luz"


# ---------------------------------------------------------------------------
# Erro identificável de leitura (R1.10).
# ---------------------------------------------------------------------------


def test_ler_caged_arquivo_ausente_levanta_erro_identificando_o_arquivo(tmp_path: Path):
    # R1.10: arquivo inexistente -> erro que nomeia o caminho.
    caminho = str(tmp_path / "nao_existe_caged.csv")

    with pytest.raises(ErroDeValidacao) as exc:
        ler_caged(caminho)

    assert "nao_existe_caged.csv" in str(exc.value)


def test_ler_municipios_arquivo_ausente_levanta_erro_identificando_o_arquivo(
    tmp_path: Path,
):
    # R1.10: idem para a base de municípios.
    caminho = str(tmp_path / "nao_existe_municipios.csv")

    with pytest.raises(ErroDeValidacao) as exc:
        ler_municipios(caminho)

    assert "nao_existe_municipios.csv" in str(exc.value)


def test_ler_caged_diretorio_no_lugar_de_arquivo_levanta_erro(tmp_path: Path):
    # R1.10: caminho aponta para um diretório (inacessível como arquivo) -> erro
    # identificando o caminho, em vez de uma exceção crua de baixo nível.
    diretorio = tmp_path / "um_diretorio"
    diretorio.mkdir()

    with pytest.raises(ErroDeValidacao) as exc:
        ler_caged(str(diretorio))

    assert "um_diretorio" in str(exc.value)


def test_ler_caged_arquivo_vazio_levanta_erro_identificando_o_arquivo(tmp_path: Path):
    # R1.10: arquivo ilegível/sem conteúdo parseável -> erro nomeando o arquivo.
    caminho = tmp_path / "caged_vazio.csv"
    caminho.write_text("", encoding="utf-8")

    with pytest.raises(ErroDeValidacao) as exc:
        ler_caged(str(caminho))

    assert "caged_vazio.csv" in str(exc.value)
