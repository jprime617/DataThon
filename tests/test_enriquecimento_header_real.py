"""Teste de regressão: `juntar` tolera o cabeçalho real da Base_de_Municipios.

O arquivo real ``Dados/Municipios_SC_limpo.csv`` nomeia a coluna de código IBGE
como ``"Código [-]"`` (sufixo " [-]") e a de nome como ``"Município [-]"``,
enquanto `src/enriquecimento.py` usa o nome canônico ``"Código"``. Este teste
constrói uma Base_de_Municipios com os nomes REAIS das colunas e verifica que
`juntar` não quebra (sem ``KeyError``) e que a `chave_municipal` é derivada
corretamente (6 primeiros dígitos do código IBGE de 7 dígitos).

Protege contra a regressão de integração em que o join falhava com
``KeyError: 'Código'`` ao rodar sobre o arquivo real.
"""

from __future__ import annotations

import pandas as pd

from src.enriquecimento import juntar


def test_juntar_tolera_cabecalho_real_com_sufixo_de_colchetes():
    # Base_de_Municipios com os nomes REAIS do arquivo (sufixo " [-]").
    df_municipios = pd.DataFrame(
        {
            "Município [-]": ["Florianópolis", "Joinville"],
            "Código [-]": ["4205407", "4209102"],  # IBGE de 7 dígitos.
            "População estimada - pessoas [2026]": [500_000, 600_000],
        }
    )
    # CAGED mínimo com o cabeçalho real (código de 6 dígitos + payload).
    df_caged = pd.DataFrame(
        {
            "município": ["420540", "420910"],
            "saldomovimentação": [10, -3],
        }
    )

    # Não deve levantar KeyError: a coluna de código é resolvida em runtime.
    resultado = juntar(df_caged, df_municipios)

    # Todo o CAGED válido é preservado (left join).
    assert resultado.total_caged == 2
    assert len(resultado.df) == 2

    # A chave de junção são os 6 primeiros dígitos do IBGE de 7 dígitos.
    chaves = sorted(resultado.df["chave_municipal"].tolist())
    assert chaves == ["420540", "420910"]

    # Ambos os registros encontraram correspondência (chave CAGED == IBGE[:6]).
    assert resultado.sem_correspondencia == 0
    # O indicador do município foi efetivamente cruzado.
    assert "População estimada - pessoas [2026]" in resultado.df.columns
