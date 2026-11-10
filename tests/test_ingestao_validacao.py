"""Testes das validações de schema do Ingestor (tarefa 3.2).

Cobrem `validar_uf` (R1.4, R1.5) e `validar_colunas` (R1.6, R1.7):
- aprovação quando o schema está correto (nenhuma exceção);
- falha com `ErroDeValidacao` reportando a contagem de UFs divergentes;
- falha com `ErroDeValidacao` listando exatamente as colunas ausentes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src import ErroDeValidacao
from src.ingestao import (
    COLUNAS_OBRIGATORIAS_CAGED,
    validar_colunas,
    validar_uf,
)


def _df_caged_valido() -> pd.DataFrame:
    """DataFrame mínimo válido: UF 42 em todas as linhas e colunas obrigatórias."""
    dados = {col: [0, 0, 0] for col in COLUNAS_OBRIGATORIAS_CAGED}
    dados["uf"] = [42, 42, 42]
    return pd.DataFrame(dados)


# --- validar_uf ------------------------------------------------------------


def test_validar_uf_aprova_quando_todas_42():
    df = pd.DataFrame({"uf": [42, 42, 42]})
    # Não deve levantar.
    assert validar_uf(df) is None


def test_validar_uf_aprova_dataframe_vazio():
    # Sem linhas divergentes, a validação passa (vacuosamente verdadeira).
    df = pd.DataFrame({"uf": pd.Series([], dtype="int64")})
    assert validar_uf(df) is None


def test_validar_uf_falha_e_conta_divergentes():
    df = pd.DataFrame({"uf": [42, 41, 42, 35, 42]})
    with pytest.raises(ErroDeValidacao) as exc:
        validar_uf(df)
    # Exatamente 2 registros divergentes (41 e 35).
    assert "2" in str(exc.value)


def test_validar_uf_falha_quando_todas_divergentes():
    df = pd.DataFrame({"uf": [35, 35, 35]})
    with pytest.raises(ErroDeValidacao) as exc:
        validar_uf(df)
    assert "3" in str(exc.value)


def test_validar_uf_falha_quando_coluna_ausente():
    df = pd.DataFrame({"outra": [1, 2, 3]})
    with pytest.raises(ErroDeValidacao) as exc:
        validar_uf(df)
    assert "uf" in str(exc.value)


# --- validar_colunas -------------------------------------------------------


def test_validar_colunas_aprova_quando_todas_presentes():
    df = _df_caged_valido()
    assert validar_colunas(df) is None


def test_validar_colunas_aprova_com_colunas_extras():
    df = _df_caged_valido()
    df["coluna_extra"] = [1, 2, 3]
    assert validar_colunas(df) is None


def test_validar_colunas_lista_exatamente_as_ausentes():
    df = _df_caged_valido()
    removidas = ["salário", "idade"]
    df = df.drop(columns=removidas)
    with pytest.raises(ErroDeValidacao) as exc:
        validar_colunas(df)
    mensagem = str(exc.value)
    # As duas removidas devem aparecer; as demais obrigatórias não.
    for col in removidas:
        assert col in mensagem
    for col in COLUNAS_OBRIGATORIAS_CAGED:
        if col not in removidas:
            assert col not in mensagem


def test_validar_colunas_falha_dataframe_sem_colunas():
    df = pd.DataFrame()
    with pytest.raises(ErroDeValidacao) as exc:
        validar_colunas(df)
    # Todas as obrigatórias devem ser listadas.
    for col in COLUNAS_OBRIGATORIAS_CAGED:
        assert col in str(exc.value)
