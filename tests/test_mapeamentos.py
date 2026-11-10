"""Testes de exemplo do carregamento de domínios (tarefa 2.2).

Verificam que cada dicionário de domínio esperado foi carregado a partir do
`Dicionario_de_dados.xlsx` e não está vazio, e que a constante `MACROFAMILIAS`
tem entre 5 e 12 itens incluindo `Não classificado`.

_Requirements: 2.5_
"""

from __future__ import annotations

import pytest

from src import mapeamentos
from src.mapeamentos import (
    CATEGORIA,
    GRAU_INSTRUCAO,
    MACROFAMILIAS,
    NAO_CLASSIFICADO,
    RACA_COR,
    SECAO_CNAE,
    SEXO,
    TAM_ESTAB_JAN,
    TIPO_MOVIMENTACAO,
    UNIDADE_SALARIO,
    carregar_dominios,
)

# Nomes das constantes de domínio esperadas (R2.5), na mesma ordem do módulo.
_NOMES_DOMINIOS = [
    "GRAU_INSTRUCAO",
    "RACA_COR",
    "SEXO",
    "TIPO_MOVIMENTACAO",
    "CATEGORIA",
    "TAM_ESTAB_JAN",
    "UNIDADE_SALARIO",
    "SECAO_CNAE",
]

_DOMINIOS_IMPORTADOS = {
    "GRAU_INSTRUCAO": GRAU_INSTRUCAO,
    "RACA_COR": RACA_COR,
    "SEXO": SEXO,
    "TIPO_MOVIMENTACAO": TIPO_MOVIMENTACAO,
    "CATEGORIA": CATEGORIA,
    "TAM_ESTAB_JAN": TAM_ESTAB_JAN,
    "UNIDADE_SALARIO": UNIDADE_SALARIO,
    "SECAO_CNAE": SECAO_CNAE,
}


@pytest.mark.parametrize("nome", _NOMES_DOMINIOS)
def test_constante_de_dominio_carregada_e_nao_vazia(nome):
    """Cada constante de domínio é um dicionário código→rótulo não vazio."""
    mapa = _DOMINIOS_IMPORTADOS[nome]
    assert isinstance(mapa, dict)
    assert mapa, f"domínio {nome} está vazio"
    # Todos os rótulos são strings não vazias.
    assert all(isinstance(rotulo, str) and rotulo for rotulo in mapa.values())


def test_carregar_dominios_retorna_todos_os_dominios_esperados():
    """`carregar_dominios()` entrega exatamente os domínios esperados, não vazios."""
    dominios = carregar_dominios()
    assert set(dominios) == set(_NOMES_DOMINIOS)
    for nome, mapa in dominios.items():
        assert isinstance(mapa, dict)
        assert mapa, f"domínio {nome} carregado vazio"


def test_secao_cnae_usa_codigos_textuais():
    """A seção CNAE usa código textual (A–Z); demais domínios, inteiros."""
    # Pelo menos uma chave da seção é textual (ex.: 'C' = indústria de transformação).
    assert any(isinstance(chave, str) for chave in SECAO_CNAE)


def test_macrofamilias_tem_entre_5_e_12_itens_incluindo_nao_classificado():
    """MACROFAMILIAS tem de 5 a 12 itens e inclui `Não classificado` (R5.2/R5.6)."""
    assert 5 <= len(MACROFAMILIAS) <= 12
    assert NAO_CLASSIFICADO in MACROFAMILIAS
    assert "Não classificado" in MACROFAMILIAS


def test_macrofamilias_sem_duplicatas():
    """O conjunto de macrofamílias não contém itens repetidos."""
    assert len(MACROFAMILIAS) == len(set(MACROFAMILIAS))


def test_caminho_dicionario_existe():
    """O caminho padrão do dicionário aponta para um arquivo existente."""
    assert mapeamentos.CAMINHO_DICIONARIO.is_file()
