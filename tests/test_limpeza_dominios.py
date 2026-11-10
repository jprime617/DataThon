"""Teste de propriedade da decodificação de domínios do Limpador (tarefa 4.4).

Valida, com Hypothesis (mín. 100 exemplos), o comportamento de
`decodificar_dominios` de `src/limpeza.py`:

- Property 7: decodificação de domínios mapeia códigos conhecidos para seus
  rótulos, preserva códigos desconhecidos e reporta a contagem correta de
  códigos não mapeados (R2.5, R2.6).

Observações de projeto:
- A função normaliza tipos antes da consulta (``1.0`` / ``"1"`` → ``1``;
  ``" C "`` → ``"C"``). Para isolar o comportamento de mapeamento/preservação,
  os geradores usam códigos conhecidos inteiros e geram códigos desconhecidos
  que, após normalização, nunca coincidem com uma chave do mapa.
- Células vazias/ausentes viram NaN (R2.7) e não são exercidas por esta
  propriedade (coberta por testes de exemplo da tarefa 4.3, se houver); aqui o
  foco é a bijeção conhecido→rótulo e a preservação+contagem dos desconhecidos.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.limpeza import decodificar_dominios


# Um mapa de domínio: código inteiro → rótulo legível (como em mapeamentos.py).
# As chaves conhecidas ficam num intervalo pequeno e fixo para que possamos
# gerar códigos desconhecidos fora dele com facilidade.
_CHAVES_CONHECIDAS = [1, 2, 3, 5, 8]
_MAPA = {codigo: f"rotulo_{codigo}" for codigo in _CHAVES_CONHECIDAS}

# Códigos conhecidos: inteiros presentes no mapa.
_codigos_conhecidos = st.sampled_from(_CHAVES_CONHECIDAS)

# Códigos desconhecidos: inteiros fora do conjunto de chaves conhecidas.
# Após normalização (int permanece int), nunca coincidem com uma chave do mapa.
_codigos_desconhecidos = st.integers(min_value=100, max_value=10_000).filter(
    lambda c: c not in _MAPA
)


@st.composite
def _sequencias_de_codigos(
    draw: st.DrawFn,
) -> tuple[list[int], list[bool]]:
    """Gera uma sequência de códigos e um rótulo de conhecido/desconhecido.

    Retorna ``(valores, conhecidos)`` em que ``valores[i]`` é o código na
    posição ``i`` e ``conhecidos[i]`` indica se esse código pertence ao mapa.
    """
    tamanho = draw(st.integers(min_value=0, max_value=15))
    valores: list[int] = []
    conhecidos: list[bool] = []

    for _ in range(tamanho):
        eh_conhecido = draw(st.booleans())
        if eh_conhecido:
            valores.append(draw(_codigos_conhecidos))
        else:
            valores.append(draw(_codigos_desconhecidos))
        conhecidos.append(eh_conhecido)

    return valores, conhecidos


# Feature: datathon-caged-sc-pipeline, Property 7: Decodificação de domínios mapeia conhecidos e preserva desconhecidos
@given(dados=_sequencias_de_codigos())
@settings(max_examples=100)
def test_prop7_decodificacao_mapeia_conhecidos_e_preserva_desconhecidos(
    dados: tuple[list[int], list[bool]],
) -> None:
    """Conhecidos viram rótulo; desconhecidos são preservados; contagem exata.

    - Cada código presente no dicionário é substituído pelo seu rótulo (R2.5).
    - Cada código ausente do dicionário tem o valor original preservado (R2.6).
    - A contagem total de códigos não mapeados reportada é igual ao número de
      posições com código fora do dicionário (R2.6).
    - A contagem por (coluna, código) soma corretamente as ocorrências de cada
      código desconhecido.

    Validates: Requirements 2.5, 2.6
    """
    valores, conhecidos = dados
    df = pd.DataFrame({"graudeinstrução": valores})

    decodificado, nao_mapeados = decodificar_dominios(
        df, {"graudeinstrução": _MAPA}
    )
    serie = decodificado["graudeinstrução"]

    # Verificação posição a posição: mapeamento de conhecidos, preservação dos
    # desconhecidos.
    for i, (valor, eh_conhecido) in enumerate(zip(valores, conhecidos)):
        if eh_conhecido:
            assert serie.iloc[i] == _MAPA[valor]
        else:
            # Código desconhecido: o valor original é preservado (R2.6).
            assert serie.iloc[i] == valor

    # Contagem total de não mapeados = número de posições desconhecidas (R2.6).
    esperado_total = sum(1 for c in conhecidos if not c)
    total_reportado = sum(r.quantidade for r in nao_mapeados)
    assert total_reportado == esperado_total

    # Contagem por código: cada registro corresponde a um código desconhecido e
    # a soma por código bate com as ocorrências observadas.
    ocorrencias_esperadas: dict[int, int] = {}
    for valor, eh_conhecido in zip(valores, conhecidos):
        if not eh_conhecido:
            ocorrencias_esperadas[valor] = (
                ocorrencias_esperadas.get(valor, 0) + 1
            )

    ocorrencias_reportadas = {
        registro.codigo: registro.quantidade for registro in nao_mapeados
    }
    assert ocorrencias_reportadas == ocorrencias_esperadas

    # Todo registro de não mapeado refere-se à coluna processada e a um código
    # genuinamente fora do dicionário.
    for registro in nao_mapeados:
        assert registro.coluna == "graudeinstrução"
        assert registro.codigo not in _MAPA
