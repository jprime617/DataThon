"""Testes de exemplo do carregamento de dados do Dashboard (tarefa 12.2).

Validam `carregar_dados` de `dashboard/app.py`, a fronteira de dados do painel,
que resolve a origem das tabelas agregadas com a estratégia de resiliência da
demonstração (R9), sem qualquer chamada de rede e usando `tmp_path` para a cópia
local em Parquet:

- leitura do Blob_Storage: com credencial presente no ambiente, lê a tabela
  agregada via `blob_loader` injetado -> ``disponivel=True`` e ``origem="blob"``
  (R9.2);
- fallback local: quando o Blob está indisponível (credencial ausente OU
  `blob_loader` levanta exceção), lê a cópia local em Parquet -> ``disponivel=True``
  e ``origem="local"`` (R9.6);
- indisponibilidade: quando AMBAS as origens falham (sem credencial + arquivo
  local ausente, ou `blob_loader` levanta + local ausente), devolve
  ``disponivel=False`` com um `motivo` e NENHUMA exceção é levantada, para que o
  chamador se abstenha de renderizar KPIs/gráficos (R7.7, R7.8).

O Blob é sempre mockado pelo `blob_loader` injetado; a credencial é exercitada
via dicionário de ambiente passado em `env=`, sem alterar o ambiente real do
processo. Nenhuma chamada de rede ocorre.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dashboard.app import (
    VAR_CREDENCIAL_AZURE,
    ResultadoCarregamento,
    carregar_dados,
)

# Connection string fictícia: para `carregar_dados` basta ser uma string não
# vazia no ambiente — a leitura real do Blob é substituída pelo `blob_loader`.
_CREDENCIAL = (
    "DefaultEndpointsProtocol=https;AccountName=fake;"
    "AccountKey=Zm9vYmFy;EndpointSuffix=core.windows.net"
)


def _tabela_agregada() -> pd.DataFrame:
    """Uma tabela agregada mínima, usada como conteúdo do Blob e do local.

    O conteúdo exato é irrelevante para o fluxo de resolução de origem; basta um
    DataFrame não trivial para afirmar que os dados retornados são os esperados.
    """
    return pd.DataFrame(
        {
            "regiao": ["420010", "420020"],
            "secao_industrial": ["C", "A"],
            "saldo_liquido": [12.5, -3.0],
        }
    )


def _gravar_parquet_local(tmp_path: Path, df: pd.DataFrame) -> Path:
    """Grava `df` como cópia local Parquet e devolve o caminho."""
    caminho = tmp_path / "caged_agregado.parquet"
    df.to_parquet(caminho)
    return caminho


# ---------------------------------------------------------------------------
# Leitura do Blob_Storage bem-sucedida (R9.2).
# ---------------------------------------------------------------------------


def test_carrega_do_blob_quando_credencial_presente(tmp_path: Path) -> None:
    """Com credencial presente, lê do Blob via `blob_loader` -> origem="blob".

    O `blob_loader` injetado registra a credencial recebida e devolve a tabela
    agregada, provando que `carregar_dados` priorizou o Blob (R9.2) sem tocar na
    cópia local (que nem existe aqui).

    Requirements: 9.2
    """
    df_blob = _tabela_agregada()
    credenciais_recebidas: list[str] = []

    def blob_loader(connection_string: str) -> pd.DataFrame:
        credenciais_recebidas.append(connection_string)
        return df_blob

    resultado = carregar_dados(
        blob_loader=blob_loader,
        caminho_local=tmp_path / "inexistente.parquet",
        env={VAR_CREDENCIAL_AZURE: _CREDENCIAL},
    )

    assert isinstance(resultado, ResultadoCarregamento)
    assert resultado.disponivel is True
    assert resultado.origem == "blob"
    assert resultado.motivo is None
    assert resultado.df is not None
    pd.testing.assert_frame_equal(resultado.df, df_blob)
    # O leitor do Blob recebeu exatamente a credencial do ambiente.
    assert credenciais_recebidas == [_CREDENCIAL]


def test_credencial_com_espacos_ao_redor_ainda_le_do_blob(tmp_path: Path) -> None:
    """Credencial com espaços ao redor é normalizada e usada para ler o Blob.

    Requirements: 9.2
    """
    df_blob = _tabela_agregada()
    credenciais_recebidas: list[str] = []

    def blob_loader(connection_string: str) -> pd.DataFrame:
        credenciais_recebidas.append(connection_string)
        return df_blob

    resultado = carregar_dados(
        blob_loader=blob_loader,
        caminho_local=tmp_path / "inexistente.parquet",
        env={VAR_CREDENCIAL_AZURE: f"  {_CREDENCIAL}  "},
    )

    assert resultado.disponivel is True
    assert resultado.origem == "blob"
    # A credencial chega ao leitor sem os espaços ao redor.
    assert credenciais_recebidas == [_CREDENCIAL]


# ---------------------------------------------------------------------------
# Fallback para a cópia local (R9.6).
# ---------------------------------------------------------------------------


def test_fallback_local_quando_credencial_ausente(tmp_path: Path) -> None:
    """Sem credencial, o Blob é ignorado e lê-se a cópia local -> origem="local".

    O `blob_loader` NÃO deve ser chamado quando não há credencial: a função pula
    direto ao fallback local (R9.6).

    Requirements: 9.6, 7.7
    """
    df_local = _tabela_agregada()
    caminho = _gravar_parquet_local(tmp_path, df_local)
    chamou_blob = False

    def blob_loader(connection_string: str) -> pd.DataFrame:
        nonlocal chamou_blob
        chamou_blob = True
        raise AssertionError("blob_loader não deveria ser chamado sem credencial")

    resultado = carregar_dados(
        blob_loader=blob_loader,
        caminho_local=caminho,
        env={},  # sem credencial
    )

    assert resultado.disponivel is True
    assert resultado.origem == "local"
    assert resultado.motivo is None
    assert resultado.df is not None
    pd.testing.assert_frame_equal(resultado.df, df_local)
    assert chamou_blob is False


def test_fallback_local_quando_blob_loader_levanta(tmp_path: Path) -> None:
    """Credencial presente mas leitura do Blob falha -> fallback local (R9.6).

    Com credencial no ambiente, `carregar_dados` tenta o Blob; como o
    `blob_loader` levanta, a falha é tratada como indisponibilidade do Blob e a
    cópia local é lida com sucesso -> origem="local".

    Requirements: 9.6, 7.7
    """
    df_local = _tabela_agregada()
    caminho = _gravar_parquet_local(tmp_path, df_local)

    def blob_loader(connection_string: str) -> pd.DataFrame:
        raise RuntimeError("falha simulada de leitura do Blob")

    resultado = carregar_dados(
        blob_loader=blob_loader,
        caminho_local=caminho,
        env={VAR_CREDENCIAL_AZURE: _CREDENCIAL},
    )

    assert resultado.disponivel is True
    assert resultado.origem == "local"
    assert resultado.motivo is None
    assert resultado.df is not None
    pd.testing.assert_frame_equal(resultado.df, df_local)


# ---------------------------------------------------------------------------
# Indisponibilidade de ambas as origens (R7.7, R7.8).
# ---------------------------------------------------------------------------


def test_indisponivel_sem_credencial_e_sem_local(tmp_path: Path) -> None:
    """Sem credencial e sem cópia local -> disponivel=False, com motivo, sem erro.

    `carregar_dados` NÃO levanta exceção quando ambas as origens falham; devolve
    um `ResultadoCarregamento` indisponível com `motivo` e sem DataFrame, para o
    chamador se abster de renderizar KPIs/gráficos (R7.7, R7.8).

    Requirements: 7.7, 7.8
    """
    inexistente = tmp_path / "nao_existe.parquet"

    resultado = carregar_dados(
        blob_loader=lambda cs: (_ for _ in ()).throw(
            AssertionError("não deveria chamar o Blob sem credencial")
        ),
        caminho_local=inexistente,
        env={},
    )

    assert resultado.disponivel is False
    assert resultado.df is None
    assert resultado.origem is None
    assert resultado.motivo  # mensagem legível não vazia
    assert str(inexistente) in resultado.motivo
    assert VAR_CREDENCIAL_AZURE in resultado.motivo


def test_indisponivel_quando_blob_falha_e_local_ausente(tmp_path: Path) -> None:
    """Blob levanta e cópia local ausente -> disponivel=False, com motivo, sem erro.

    Requirements: 7.7, 7.8
    """
    inexistente = tmp_path / "nao_existe.parquet"

    def blob_loader(connection_string: str) -> pd.DataFrame:
        raise RuntimeError("Blob fora do ar")

    resultado = carregar_dados(
        blob_loader=blob_loader,
        caminho_local=inexistente,
        env={VAR_CREDENCIAL_AZURE: _CREDENCIAL},
    )

    assert resultado.disponivel is False
    assert resultado.df is None
    assert resultado.origem is None
    assert resultado.motivo
    # O motivo acumula as duas causas: Blob indisponível e cópia local ausente.
    assert "Blob" in resultado.motivo
    assert str(inexistente) in resultado.motivo


def test_credencial_apenas_espacos_cai_no_fallback_e_indisponibiliza(
    tmp_path: Path,
) -> None:
    """Credencial só com espaços conta como ausente: pula o Blob, tenta o local.

    Com credencial em branco e sem cópia local, o resultado é indisponível sem
    jamais chamar o `blob_loader` (R7.8).

    Requirements: 7.8
    """
    inexistente = tmp_path / "nao_existe.parquet"
    chamou_blob = False

    def blob_loader(connection_string: str) -> pd.DataFrame:
        nonlocal chamou_blob
        chamou_blob = True
        return _tabela_agregada()

    resultado = carregar_dados(
        blob_loader=blob_loader,
        caminho_local=inexistente,
        env={VAR_CREDENCIAL_AZURE: "   "},
    )

    assert chamou_blob is False
    assert resultado.disponivel is False
    assert resultado.motivo is not None
