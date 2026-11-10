"""Teste de exemplo da persistência do prompt no agrupamento de CBOs (tarefa 8.7).

Cobre o requisito R5.8: o `Classificador_de_CBO` registra o prompt utilizado no
agrupamento *junto ao* mapeamento gerado (`cbo_macrofamilias.csv`). Verifica que,
ao executar `classificar_cbos`, além do CSV do mapeamento é gravado um arquivo
irmão com o prompt empregado e que o conteúdo desse arquivo:

- corresponde exatamente ao prompt produzido por `montar_prompt(...)` para o
  conjunto de CBOs distintos classificados (determinismo/auditoria — R5.8);
- é não vazio e contém o conjunto fechado de macrofamílias (`MACROFAMILIAS`).

O LLM é sempre mockado por `ClienteFake` (sem rede), o CSV é gravado em
`tmp_path` e a credencial `LLM_API_KEY` é injetada via `env=`, sem alterar o
ambiente real do processo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.cbo_ia import (
    COLUNA_CBO,
    NAO_CLASSIFICADO,
    VAR_CREDENCIAL_LLM,
    classificar_cbos,
    extrair_cbos,
    montar_prompt,
)
from src.mapeamentos import MACROFAMILIAS

# Uma macrofamília válida qualquer (não o fallback) para a resposta simulada.
_FAMILIA_VALIDA = next(f for f in MACROFAMILIAS if f != NAO_CLASSIFICADO)


class ClienteFake:
    """Cliente LLM simulado, sem chamada de rede, que ecoa um mapa configurado.

    Devolve sempre o mesmo objeto JSON `{cbo: macrofamilia}` fornecido na
    construção, independentemente do prompt recebido. Guarda os prompts e conta
    as chamadas, de modo que o teste possa correlacionar o prompt enviado ao
    arquivo persistido, se necessário.
    """

    def __init__(self, mapa: dict[str, str]):
        self._resposta = json.dumps(mapa)
        self.chamadas = 0
        self.prompts: list[str] = []

    def classificar(self, prompt: str, *, timeout: int) -> str:
        self.chamadas += 1
        self.prompts.append(prompt)
        return self._resposta


def _df_caged() -> pd.DataFrame:
    """DataFrame CAGED-like com códigos de ocupação distintos e repetidos."""
    return pd.DataFrame(
        {COLUNA_CBO: ["223505", "317210", "223505", "411005"]}
    )


def test_prompt_e_gravado_junto_ao_csv_do_mapeamento(tmp_path):
    # R5.8: o prompt usado é persistido ao lado do `cbo_macrofamilias.csv`.
    df = _df_caged()
    cbos = extrair_cbos(df)
    client = ClienteFake({codigo: _FAMILIA_VALIDA for codigo in cbos})
    destino = tmp_path / "cbo_macrofamilias.csv"

    resultado = classificar_cbos(
        df,
        client,
        destino_csv=str(destino),
        env={VAR_CREDENCIAL_LLM: "chave-valida"},
    )

    # O CSV do mapeamento foi gravado no destino solicitado.
    assert Path(resultado.caminho_csv) == destino
    assert destino.exists()

    # Existe um arquivo irmão do prompt, na MESMA pasta do CSV ("junto ao").
    caminho_prompt = Path(resultado.caminho_prompt)
    assert caminho_prompt.exists()
    assert caminho_prompt.parent == destino.parent
    # O nome do prompt deriva do nome do CSV (arquivo irmão de auditoria).
    assert caminho_prompt.name.startswith(destino.name)


def test_conteudo_do_prompt_corresponde_a_montar_prompt(tmp_path):
    # O conteúdo gravado é exatamente o prompt determinístico do conjunto de CBOs.
    df = _df_caged()
    cbos = extrair_cbos(df)
    client = ClienteFake({codigo: _FAMILIA_VALIDA for codigo in cbos})
    destino = tmp_path / "cbo_macrofamilias.csv"

    resultado = classificar_cbos(
        df,
        client,
        destino_csv=str(destino),
        env={VAR_CREDENCIAL_LLM: "chave-valida"},
    )

    conteudo = Path(resultado.caminho_prompt).read_text(encoding="utf-8")
    prompt_esperado = montar_prompt(cbos)

    # O prompt persistido corresponde ao produzido por `montar_prompt`.
    assert conteudo == prompt_esperado
    # É não vazio.
    assert conteudo.strip() != ""
    # Contém o conjunto fechado de macrofamílias (auditoria — R5.8).
    for familia in MACROFAMILIAS:
        assert familia in conteudo
