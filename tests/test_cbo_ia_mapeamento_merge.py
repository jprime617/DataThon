"""Testes de propriedade do mapeamento e merge do Classificador_de_CBO (tarefa 8.6).

Implementam as propriedades 21 e 22 do design com Hypothesis (mín. 100 exemplos,
perfil `datathon` carregado em `conftest.py`), com tag de rastreabilidade
obrigatória por propriedade. O LLM_Externo é sempre **mockado** (sem rede) por
um cliente simulado que devolve respostas JSON arbitrárias, e o CSV do
mapeamento é gravado em um diretório temporário criado dentro de cada exemplo
(via `tempfile`), para não acoplar fixtures function-scoped do pytest ao
Hypothesis.

- Property 21: Mapeamento CBO é único e dentro do conjunto, com fallback
  — Validates: Requirements 5.2, 5.4, 5.6
- Property 22: Contagem de CBOs sem correspondência no merge é exata
  — Validates: Requirements 5.5

Property 21 gera um conjunto de códigos CBO distintos e um cliente simulado cuja
resposta mistura macrofamílias válidas, macrofamílias inválidas (fora do
conjunto) e códigos ausentes; verifica que `classificar_cbos` consolida
exatamente uma entrada por CBO distinto, que todo valor pertence a
`MACROFAMILIAS`, e que todo código sem macrofamília válida recebe
`Não classificado`.

Property 22 gera uma base cruzada com a coluna `cbo2002ocupação` (códigos
válidos, nulos e vazios) e um cliente simulado; verifica que
`ClassificacaoResult.sem_correspondencia` é exatamente o número de linhas da
base cujo código normalizado não está presente no mapeamento consolidado.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.cbo_ia import (
    COLUNA_CBO,
    COLUNA_MACROFAMILIA,
    _normalizar_cbo,
    classificar_cbos,
)
from src.mapeamentos import MACROFAMILIAS, NAO_CLASSIFICADO

# Conjunto fechado de macrofamílias válidas (para asserção).
_VALIDAS = frozenset(MACROFAMILIAS)

# Macrofamílias válidas que NÃO são o fallback, para exercitar o caminho feliz.
_VALIDAS_SEM_FALLBACK = [m for m in MACROFAMILIAS if m != NAO_CLASSIFICADO]

# Rótulos inválidos (fora do conjunto fechado) que devem cair no fallback.
_INVALIDAS = st.sampled_from(
    ["Inexistente", "engenharia", "", "   ", "Outros", "XPTO"]
)

# Códigos CBO distintos como texto (dígitos).
_CBO_TEXTO = st.text(alphabet="0123456789", min_size=1, max_size=6)


class ClienteLLMSimulado:
    """Cliente do LLM_Externo simulado: devolve um JSON pré-definido, sem rede.

    A resposta é um dicionário ``{cbo: rótulo}`` arbitrário, possivelmente com
    rótulos inválidos (fora do conjunto) e sem alguns códigos do lote — o que
    exercita o fallback `Não classificado` de `classificar_lote`.
    """

    def __init__(self, resposta_por_cbo: dict[str, str]):
        self._resposta_por_cbo = resposta_por_cbo
        self.chamadas = 0

    def classificar(self, prompt: str, *, timeout: int) -> str:
        self.chamadas += 1
        # Responde apenas os códigos presentes neste lote (os que aparecem no
        # prompt), para simular omissões realistas.
        corpo = {
            cbo: {"macrofamilia": rotulo, "justificativa": "teste"}
            for cbo, rotulo in self._resposta_por_cbo.items()
            if cbo in prompt
        }
        return json.dumps(corpo)


# Estratégia: um rótulo de resposta do LLM — válido, inválido, ou "ausente".
# O sentinela ``None`` sinaliza que o código NÃO será incluído na resposta.
_ROTULO_RESPOSTA = st.one_of(
    st.sampled_from(_VALIDAS_SEM_FALLBACK),
    _INVALIDAS,
    st.none(),
)


# ---------------------------------------------------------------------------
# Property 21: Mapeamento CBO é único e dentro do conjunto, com fallback.
# ---------------------------------------------------------------------------


# Feature: datathon-caged-sc-pipeline, Property 21: Mapeamento CBO é único e dentro do conjunto, com fallback
@settings(max_examples=100)
@given(
    respostas=st.dictionaries(
        keys=_CBO_TEXTO,
        values=_ROTULO_RESPOSTA,
        min_size=0,
        max_size=40,
    )
)
def test_prop21_mapeamento_unico_dentro_do_conjunto_com_fallback(respostas):
    # Feature: datathon-caged-sc-pipeline, Property 21: Mapeamento CBO é único e dentro do conjunto, com fallback
    # Validates: Requirements 5.2, 5.4, 5.6
    cbos = list(respostas.keys())
    # A base repete códigos para garantir que a consolidação é por CBO distinto.
    df = pd.DataFrame({COLUNA_CBO: pd.Series(cbos + cbos, dtype=object)})

    # O cliente só devolve os rótulos não-None (os None simulam código ausente).
    resposta_cliente = {
        cbo: rotulo for cbo, rotulo in respostas.items() if rotulo is not None
    }
    client = ClienteLLMSimulado(resposta_cliente)

    with tempfile.TemporaryDirectory() as tmp:
        destino = str(Path(tmp) / "cbo_macrofamilias.csv")
        resultado = classificar_cbos(
            df, client, destino_csv=destino, verificar_credencial=False
        )

    mapeamento = resultado.mapeamento

    # (R5.4) Exatamente uma entrada por CBO distinto presente na base.
    assert set(mapeamento.keys()) == set(cbos)
    assert len(mapeamento) == len(set(cbos))

    # (R5.2) Toda macrofamília atribuída pertence ao conjunto fechado.
    for valor in mapeamento.values():
        assert valor in _VALIDAS

    # (R5.6) Fallback exato: código sem rótulo válido recebe `Não classificado`,
    # e código com rótulo válido preserva exatamente esse rótulo.
    for cbo in cbos:
        rotulo = respostas[cbo]
        if rotulo in _VALIDAS_SEM_FALLBACK:
            assert mapeamento[cbo] == rotulo
        else:
            # Ausente (None) ou inválido → fallback.
            assert mapeamento[cbo] == NAO_CLASSIFICADO


# ---------------------------------------------------------------------------
# Property 22: Contagem de CBOs sem correspondência no merge é exata.
# ---------------------------------------------------------------------------

# Elemento da coluna da base: código válido (texto) ou nulo/vazio.
_ELEMENTO_BASE = st.one_of(
    _CBO_TEXTO,
    st.sampled_from([None, float("nan"), "", "   "]),
)


# Feature: datathon-caged-sc-pipeline, Property 22: Contagem de CBOs sem correspondência no merge é exata
@settings(max_examples=100)
@given(
    valores=st.lists(_ELEMENTO_BASE, min_size=0, max_size=60),
    rotulos=st.lists(_ROTULO_RESPOSTA, min_size=0, max_size=40),
)
def test_prop22_contagem_sem_correspondencia_exata(valores, rotulos):
    # Feature: datathon-caged-sc-pipeline, Property 22: Contagem de CBOs sem correspondência no merge é exata
    # Validates: Requirements 5.5
    df = pd.DataFrame({COLUNA_CBO: pd.Series(valores, dtype=object)})

    # Monta uma resposta do LLM associando alguns códigos distintos da base a
    # rótulos (válidos/ inválidos/ ausentes), para que o mapeamento consolidado
    # cubra parte dos códigos e deixe outros de fora.
    distintos = []
    vistos: set[str] = set()
    for valor in valores:
        codigo = _normalizar_cbo(valor)
        if codigo is not None and codigo not in vistos:
            vistos.add(codigo)
            distintos.append(codigo)

    resposta_cliente: dict[str, str] = {}
    for codigo, rotulo in zip(distintos, rotulos):
        if rotulo is not None:
            resposta_cliente[codigo] = rotulo
    client = ClienteLLMSimulado(resposta_cliente)

    with tempfile.TemporaryDirectory() as tmp:
        destino = str(Path(tmp) / "cbo_macrofamilias.csv")
        resultado = classificar_cbos(
            df, client, destino_csv=destino, verificar_credencial=False
        )

    mapeamento = resultado.mapeamento

    # Contagem independente: linhas cujo código normalizado não está presente
    # como chave no mapeamento consolidado (inclui nulos/vazios, que nunca
    # entram no mapeamento por construção — R5.1/R5.4).
    esperado = 0
    for valor in valores:
        codigo = _normalizar_cbo(valor)
        if codigo is None or codigo not in mapeamento:
            esperado += 1

    # (R5.5) A contagem reportada é exatamente igual à contagem real.
    assert resultado.sem_correspondencia == esperado

    # Consistência com a base enriquecida: a contagem equivale ao nº de linhas
    # com macrofamília ausente após o merge.
    ausentes_no_merge = int(
        resultado.df_enriquecido[COLUNA_MACROFAMILIA].isna().sum()
    )
    assert resultado.sem_correspondencia == ausentes_no_merge
