"""Camada de dados do dashboard v2: colunas aditivas, setor, nível e perfil."""

from __future__ import annotations

import math

import pandas as pd

from src.agregador import (
    COLUNAS_ADITIVAS,
    agregar,
    agregar_perfil,
    preparar_base,
)
from src.mapeamentos import MICRORREGIAO_POR_MUNICIPIO


def _base() -> pd.DataFrame:
    """Seis movimentações em Joinville (420910): C-têxtil, C-metal e F."""
    return pd.DataFrame(
        {
            "chave_municipal": ["420910"] * 6,
            "seção": ["C", "C", "C", "C", "F", "F"],
            "subclasse": ["1412601", "1412601", "2511000", "2511000", "4120400", "4120400"],
            "macrofamilia": ["Têxtil, confecção, couro e calçados"] * 2
            + ["Metalmecânica e eletroeletrônica"] * 2
            + ["Construção civil e extração"] * 2,
            "nivel_qualificacao": ["Qualificado"] * 4 + ["Básico"] * 2,
            "competênciamov": ["202509"] * 6,
            "saldomovimentação": [1, -1, 1, -1, -1, -1],
            "tipomovimentação": [97, 40, 97, 31, 40, "Desligamento a pedido"],
            "salário": [2000.0, 3000.0, float("nan"), 4000.0, 1500.0, 1700.0],
            "escolaridade_ordinal": [7.0, 9.0, 7.0, float("nan"), 4.0, 5.0],
        }
    )


def _municipios() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "chave_municipal": ["420910"],
            "Município [-]": ["Joinville"],
            "População estimada - pessoas [2026]": [650000.0],
        }
    )


def test_setor_abre_a_transformacao_e_mantem_as_demais_secoes():
    base = preparar_base(_base())
    assert list(base["setor"]) == [
        "Têxtil, confecção e calçados", "Têxtil, confecção e calçados",
        "Metalurgia e produtos de metal", "Metalurgia e produtos de metal",
        "F", "F",
    ]


def test_desligamento_a_pedido_aceita_codigo_e_rotulo():
    base = preparar_base(_base())
    # Linhas 1 (código 40), 4 (40) e 5 (rótulo decodificado) são a pedido.
    assert base["desligamentos_a_pedido"].tolist() == [0, 1, 0, 0, 1, 1]


def test_desligamentos_descontados_tiram_40_50_60_80():
    df = _base()
    df["tipomovimentação"] = [97, 31, 97, 50, 60, "Desligamento por transferência"]
    base = preparar_base(df)
    # Só a demissão sem justa causa (31) entra na rotatividade descontada.
    assert base["desligamentos_descontados"].tolist() == [0, 1, 0, 0, 0, 0]
    # O a pedido (40) da base original também sai.
    assert preparar_base(_base())["desligamentos_descontados"].tolist() == [0, 0, 0, 1, 0, 0]


def test_colunas_aditivas_somam_o_total_da_base():
    agregado = agregar(_base(), _municipios())
    assert agregado["admissoes"].sum() == 2
    assert agregado["desligamentos"].sum() == 4
    assert agregado["desligamentos_a_pedido"].sum() == 3
    # Salário NaN não entra na soma nem no contador (regra das médias R4.6).
    assert agregado["n_salario_admissao"].sum() == 1
    assert math.isclose(agregado["soma_salario_desligamento"].sum(), 3000 + 4000 + 1500 + 1700)
    assert agregado["n_escolaridade_desligamento"].sum() == 3
    # Saldo das colunas aditivas == saldo R6.
    assert (agregado["admissoes"] - agregado["desligamentos"]).sum() == agregado["saldo_liquido"].sum()


def test_schema_v2_so_acrescenta_colunas_e_traz_nome_e_microrregiao():
    agregado = agregar(_base(), _municipios())
    assert agregado.columns[0] == "regiao"
    assert set(COLUNAS_ADITIVAS) <= set(agregado.columns)
    assert set(agregado["municipio_nome"]) == {"Joinville"}
    assert set(agregado["microrregiao"]) == {MICRORREGIAO_POR_MUNICIPIO["420910"]}
    assert agregado["escopo_industrial"].all()


def test_microrregiao_cobre_os_295_municipios_em_20_microrregioes():
    assert len(MICRORREGIAO_POR_MUNICIPIO) == 295
    assert len(set(MICRORREGIAO_POR_MUNICIPIO.values())) == 20


def test_perfil_tem_medianas_por_faixa_e_contagens_aditivas():
    perfil = agregar_perfil(_base())
    assert perfil["admissoes"].sum() == 2
    construcao = perfil[perfil["setor"] == "F"]
    # Desligados da construção: 1500 (fund. incompleto) e 1700 (fund. completo).
    por_faixa = construcao.set_index("faixa_escolaridade")["mediana_salario_desligamento"]
    assert por_faixa["Até fundamental incompleto"] == 1500
    assert por_faixa["Fundamental completo"] == 1700
