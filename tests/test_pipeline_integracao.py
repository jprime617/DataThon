"""Teste de integração ponta a ponta do pipeline (tarefa 13.2 — R8.1).

Este teste exercita o pipeline completo sobre um **fixture reduzido**, na mesma
ordem do notebook orquestrador (tarefa 13.1):

    ingestão → limpeza → junção → CBO/LLM → agregação → upload

O LLM_Externo e o Azure são **mockados** (nenhuma chamada de rede): um
`ClienteLLM` simulado devolve macrofamílias válidas e um `ClienteContainer`
simulado registra os blobs enviados. Todos os artefatos usam `tmp_path`.

O objetivo é provar que o pipeline roda de ponta a ponta sem intervenção manual
entre etapas, produzindo os artefatos de saída consumidos pelo dashboard (R8.1):

- ``caged_bruto.parquet`` gravado pela ingestão;
- ``cbo_macrofamilias.csv`` (+ prompt) gravado pela etapa de CBO/LLM;
- ``caged_agregado.parquet`` exportado e relegível com o schema agregado;
- o cliente Azure simulado recebeu o blob da tabela agregada.

As fontes são construídas em disco (CSV) no formato real: CAGED com ``sep=';'`` e
``decimal=','`` e municípios com ``sep=','``. Mapas de domínio mínimos cobrem
exatamente os códigos do fixture (não dependemos do dicionário real).
"""

from __future__ import annotations

import json

from pathlib import Path

import pandas as pd

from src.agregador import (
    COLUNAS_ADITIVAS,
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
    COLUNA_SALARIO_MEDIO_ADMISSAO,
    COLUNA_SALARIO_MEDIO_DESLIGAMENTO,
    COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO,
    agregar,
    exportar,
)
from src.azure_upload import VAR_CREDENCIAL_AZURE, upload_tabelas
from src.cbo_ia import NAO_CLASSIFICADO, classificar_cbos
from src.enriquecimento import chave_municipal_ibge, juntar
from src.ingestao import executar_ingestao, ler_caged, ler_municipios
from src.limpeza import limpar

# Connection string fictícia, porém com o prefixo esperado para passar na guarda
# de credencial do Azure sem tocar na rede (R8.7/R9.3 cobertos por 11.2).
_CONN_VALIDA = (
    "DefaultEndpointsProtocol=https;AccountName=fake;"
    "AccountKey=Zm9vYmFy;EndpointSuffix=core.windows.net"
)
_CONTAINER = "tabelas-agregadas"


# ---------------------------------------------------------------------------
# Dublês do LLM e do Azure (sem rede)
# ---------------------------------------------------------------------------


class ClienteLLMFake:
    """`ClienteLLM` simulado: classifica cada CBO do prompt de forma determinística.

    Lê os códigos listados no prompt (uma linha por código, na seção "Códigos
    CBO a classificar") e devolve um JSON ``{cbo: macrofamilia}`` com uma
    macrofamília **válida** para cada código, alternando entre duas famílias do
    conjunto fechado. Não faz rede e registra quantas vezes foi chamado.
    """

    def __init__(self, familias: list[str]) -> None:
        self._familias = familias
        self.chamadas = 0

    def classificar(self, prompt: str, *, timeout: int) -> str:
        self.chamadas += 1
        # Os códigos aparecem entre os marcadores do prompt montado por
        # `montar_prompt`: logo após "Códigos CBO a classificar:" e antes da
        # instrução final de resposta JSON.
        marcador = "Códigos CBO a classificar:\n"
        inicio = prompt.index(marcador) + len(marcador)
        fim = prompt.index("\n\nResponda", inicio)
        # Cada linha é "código | descrição | nivel_cbo | família sugerida".
        codigos = [
            linha.split(" | ")[0]
            for linha in prompt[inicio:fim].splitlines()
            if linha.strip()
        ]
        return json.dumps(
            {
                codigo: {
                    "macrofamilia": self._familias[i % len(self._familias)],
                    "justificativa": "teste",
                }
                for i, codigo in enumerate(codigos)
            }
        )


class ContainerFake:
    """`ClienteContainer` simulado: guarda os blobs enviados, sem rede."""

    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, bool]] = []

    def upload_blob(self, name: str, data: bytes, *, overwrite: bool = False) -> object:
        self.uploads.append((name, data, overwrite))
        return object()


class FabricaFake:
    """Fábrica de `ContainerFake` simulada: devolve sempre o mesmo cliente."""

    def __init__(self, cliente: ContainerFake) -> None:
        self._cliente = cliente
        self.chamadas = 0

    def __call__(self, connection_string: str, container: str) -> ContainerFake:
        self.chamadas += 1
        return self._cliente


# ---------------------------------------------------------------------------
# Fixture reduzido (CAGED + municípios) em disco, no formato real
# ---------------------------------------------------------------------------

# Códigos municipais do fixture: CAGED usa 6 dígitos; a Base_de_Municipios usa o
# IBGE de 7 dígitos cujos 6 primeiros são a Chave_Municipal.
_MUN_A_CAGED = "420010"
_MUN_A_IBGE = "4200101"  # 6 primeiros -> 420010
_MUN_B_CAGED = "420020"
_MUN_B_IBGE = "4200200"  # 6 primeiros -> 420020

# Nomes exatos dos indicadores socioeconômicos (cabeçalho de Municipios_SC).
_COL_POP = "População estimada - pessoas [2026]"
_COL_IDHM = "IDHM <span>Índice de desenvolvimento humano municipal</span> [2010]"
_COL_PIB = "PIB per capita - R$ [2023]"

# Mapas de domínio mínimos cobrindo exatamente os códigos do fixture (R2.5).
# A chave da seção CNAE é textual; os demais domínios usam código inteiro.
#
# `tamestabjan` está incluída de propósito, como no pipeline real: é um domínio
# categórico que R2.5 manda decodificar para o rótulo de faixa.
_MAPAS = {
    "seção": {"C": "Indústria de transformação", "F": "Construção"},
    "graudeinstrução": {7: "Ensino médio completo", 9: "Superior completo"},
    "raçacor": {2: "Branca", 4: "Parda"},
    "sexo": {1: "Homem", 3: "Mulher"},
    "tamestabjan": {4: "De 10 a 19", 5: "De 20 a 49"},
}


def _escrever_caged(caminho: Path) -> int:
    """Escreve um CAGED reduzido (sep=';', decimal=',') e devolve o nº de linhas.

    Inclui todas as colunas obrigatórias do Ingestor, ``uf == 42`` em todas as
    linhas, ``tamestabjan`` como **código de faixa** (5 = "De 20 a 49",
    4 = "De 10 a 19") — igual ao arquivo real —, competências dentro do intervalo
    ``[202509, 202608]`` e salários no formato brasileiro, que é o formato real
    do CAGED. Cada
    município tem admissões e desligamentos em 2 meses para exercitar saldo
    e as séries mensais.
    """
    linhas = [
        # (competência, município, seção, subclasse, saldo, cbo, grau, idade,
        #  raça, sexo, salário, valorsaláriofixo, tamestabjan, uf)
        (202509, _MUN_A_CAGED, "C", "1091101", 1, "848505", 7, 30, 2, 1, "2018,00", "2018,00", 5, 42),
        (202509, _MUN_A_CAGED, "C", "1091101", -1, "848505", 7, 41, 4, 3, "1900,50", "1900,50", 5, 42),
        (202510, _MUN_A_CAGED, "C", "1091101", 1, "782510", 9, 28, 2, 3, "3500,00", "3500,00", 5, 42),
        (202510, _MUN_A_CAGED, "C", "1091101", 1, "848505", 7, 35, 4, 1, "2100,00", "2100,00", 5, 42),
        (202509, _MUN_B_CAGED, "F", "4120400", 1, "715210", 7, 22, 4, 1, "1600,00", "1600,00", 4, 42),
        (202510, _MUN_B_CAGED, "F", "4120400", -1, "715210", 7, 50, 2, 1, "1750,25", "1750,25", 4, 42),
    ]
    colunas = [
        "competênciamov", "município", "seção", "subclasse", "saldomovimentação",
        "cbo2002ocupação", "graudeinstrução", "idade", "raçacor", "sexo",
        "salário", "valorsaláriofixo", "tamestabjan", "uf",
    ]
    df = pd.DataFrame(linhas, columns=colunas)
    # Formato real do CAGED: separador ';' e decimal ',' (R1.1). Os salários já
    # estão em texto BR; o to_csv apenas usa ';' como separador de campos.
    df.to_csv(caminho, sep=";", index=False, encoding="utf-8")
    return len(df)


def _escrever_municipios(caminho: Path) -> int:
    """Escreve a Base_de_Municipios reduzida (sep=',') e devolve o nº de linhas.

    Os indicadores usam **ponto decimal**, como o `Municipios_SC_limpo.csv` real
    exportado do IBGE (``0.750``, ``35000.00``) — e não o formato brasileiro. O
    marcador ``-`` de um PIB ausente exercita R2.4 → NaN. Códigos IBGE de 7
    dígitos cujos 6 primeiros casam com os códigos de 6 dígitos do CAGED.
    """
    linhas = [
        ("Município A", _MUN_A_IBGE, "15000", "0.750", "35000.00"),
        ("Município B", _MUN_B_IBGE, "8000", "0.680", "-"),
    ]
    colunas = ["Município", "Código", _COL_POP, _COL_IDHM, _COL_PIB]
    df = pd.DataFrame(linhas, columns=colunas)
    df.to_csv(caminho, sep=",", index=False, encoding="utf-8")
    return len(df)


# ---------------------------------------------------------------------------
# Teste de integração ponta a ponta
# ---------------------------------------------------------------------------


def test_pipeline_ponta_a_ponta_sobre_fixture_pequeno(tmp_path: Path) -> None:
    """Roda o pipeline inteiro sobre o fixture e verifica os artefatos (R8.1).

    Encadeia ingestão → limpeza → junção → CBO/LLM → agregação → upload com LLM e
    Azure mockados, e afirma que:

    - a ingestão gravou ``caged_bruto.parquet`` e contou as linhas corretamente;
    - a etapa de CBO/LLM gravou ``cbo_macrofamilias.csv`` (+ prompt) com
      macrofamílias válidas e o cliente LLM foi efetivamente chamado;
    - a agregação produziu linhas e a exportação gerou ``caged_agregado.parquet``
      relegível com o schema agregado esperado;
    - o cliente Azure simulado recebeu o blob da tabela agregada (R9.1).
    """
    # --- Prepara as fontes do fixture em disco ------------------------------
    origem = tmp_path / "Dados"
    origem.mkdir()
    caminho_caged = origem / "Novo_Caged_MOV_Limpo.csv"
    caminho_municipios = origem / "Municipios_SC_limpo.csv"
    n_caged = _escrever_caged(caminho_caged)
    n_municipios = _escrever_municipios(caminho_municipios)

    processados = tmp_path / "data_processed"
    processados.mkdir()
    destino_bruto = processados / "caged_bruto.parquet"

    # --- Etapa 1: Ingestão (R1) ---------------------------------------------
    resultado_ingestao = executar_ingestao(
        str(caminho_caged), str(caminho_municipios), str(destino_bruto)
    )
    assert destino_bruto.exists(), "caged_bruto.parquet deveria ter sido gravado"
    assert resultado_ingestao.linhas_caged == n_caged
    assert resultado_ingestao.linhas_municipios == n_municipios

    # O bruto é relegível e tem as colunas do CAGED (sem Unnamed:*).
    caged_bruto = pd.read_parquet(destino_bruto)
    assert len(caged_bruto) == n_caged
    assert not [c for c in caged_bruto.columns if str(c).startswith("Unnamed")]

    # --- Etapa 2: Limpeza (R2) ----------------------------------------------
    # Relê as fontes como o notebook faria (bruto para o CAGED; municípios da origem).
    df_caged = ler_caged(str(caminho_caged))
    df_municipios = ler_municipios(str(caminho_municipios))
    limpeza = limpar(df_caged, df_municipios, _MAPAS)

    # Competências do fixture estão todas no intervalo -> nada excluído.
    assert limpeza.excluidos_competencia == 0
    assert len(limpeza.caged) == n_caged
    # Salários viraram float; a seção foi decodificada para rótulo legível.
    assert limpeza.caged["salário"].dtype.kind == "f"
    assert set(limpeza.caged["seção"]) <= {
        "Indústria de transformação",
        "Construção",
    }
    # O marcador "-" do PIB do município B virou NaN (R2.4).
    assert limpeza.municipios[_COL_PIB].isna().sum() == 1

    # --- Etapa 3: Junção relacional (R3) ------------------------------------
    juncao = juntar(limpeza.caged, limpeza.municipios)
    # Todo o CAGED válido preservado e todos os municípios correspondem.
    assert juncao.total_caged == n_caged
    assert juncao.sem_correspondencia == 0
    assert juncao.excluidos_caged == 0
    assert "chave_municipal" in juncao.df.columns

    # --- Etapa 4: CBO/LLM mockado (R5) --------------------------------------
    destino_cbo = processados / "cbo_macrofamilias.csv"
    cliente_llm = ClienteLLMFake(
        ["Operação de linha e processo", "Técnicos industriais, engenharia e TI"]
    )
    classificacao = classificar_cbos(
        juncao.df,
        cliente_llm,
        destino_csv=str(destino_cbo),
        # Injeta a credencial do LLM para a guarda não interromper (R8.6).
        env={"LLM_API_KEY": "chave-fake-de-teste"},
    )
    # O LLM foi chamado (ao menos um lote) e o CSV + prompt foram gravados.
    assert cliente_llm.chamadas >= 1
    assert destino_cbo.exists(), "cbo_macrofamilias.csv deveria ter sido gravado"
    assert Path(classificacao.caminho_prompt).exists()

    # O mapeamento persistido tem 1 linha por CBO, todas com macrofamília válida.
    mapa_csv = pd.read_csv(destino_cbo, dtype=str)
    assert list(mapa_csv.columns) == [
        "cbo2002ocupação", "descricao", "macrofamilia",
        "nivel_qualificacao", "lideranca", "justificativa",
    ]
    assert mapa_csv["cbo2002ocupação"].is_unique
    familias_validas = {
        "Operação de linha e processo",
        "Técnicos industriais, engenharia e TI",
        NAO_CLASSIFICADO,
    }
    assert set(mapa_csv["macrofamilia"]) <= familias_validas
    # Todo CBO do fixture foi classificado -> sem linhas órfãs no merge.
    assert classificacao.sem_correspondencia == 0
    assert "macrofamilia" in classificacao.df_enriquecido.columns

    # --- Etapa 5: Agregação + exportação (R6) -------------------------------
    # O Agregador anexa os indicadores por `chave_municipal`; o orquestrador
    # deriva essa chave na Base_de_Municipios a partir do IBGE de 7 dígitos
    # (os 6 primeiros), do mesmo modo que a Junta_Relacional faz internamente.
    municipios_agg = limpeza.municipios.copy()
    municipios_agg["chave_municipal"] = municipios_agg["Código"].map(
        chave_municipal_ibge
    )

    # O CAGED é lido como texto na ingestão; o orquestrador coage para número o
    # saldo antes de agregar. O Turnover não precisa de mais nada: o denominador
    # é `max(admissões, desligamentos)`, contado do próprio saldo.
    base_metricas = classificacao.df_enriquecido.copy()
    base_metricas["saldomovimentação"] = pd.to_numeric(
        base_metricas["saldomovimentação"], errors="coerce"
    )

    agregado = agregar(base_metricas, municipios_agg)
    assert not agregado.empty, "a agregação deveria produzir ao menos 1 recorte"

    destino_agregado = processados / "caged_agregado.parquet"
    exportar(agregado, destino_agregado)
    assert destino_agregado.exists(), "caged_agregado.parquet deveria existir"

    # O agregado é relegível e tem exatamente o schema esperado (R6).
    relido = pd.read_parquet(destino_agregado)
    schema_esperado = [
        COLUNA_REGIAO,
        COLUNA_MUNICIPIO,
        COLUNA_SECAO_INDUSTRIAL,
        COLUNA_MACROFAMILIA_CBO,
        COLUNA_MES,
        COLUNA_SALDO_LIQUIDO,
        COLUNA_SALDO_POR_10K,
        COLUNA_SALARIO_MEDIO_ADMISSAO,
        COLUNA_SALARIO_MEDIO_DESLIGAMENTO,
        COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO,
        COLUNA_POPULACAO_2026,
        COLUNA_IDHM_2010,
        COLUNA_PIB_PER_CAPITA_2023,
    ]
    # Compatibilidade com o app antigo: as colunas R6 vêm primeiro, na mesma
    # ordem; as do dashboard v2 só se acrescentam depois delas.
    assert list(relido.columns)[: len(schema_esperado)] == schema_esperado
    assert set(COLUNAS_ADITIVAS) <= set(relido.columns)
    assert {"microrregiao", "setor", "nivel_qualificacao", "escopo_industrial"} <= set(
        relido.columns
    )
    assert len(relido) == len(agregado)
    # Indicadores municipais anexados: população do município A presente (R6.6).
    assert relido[COLUNA_POPULACAO_2026].notna().any()

    # O IDHM preserva a escala original [0, 1] — a conversão não pode tratar o
    # ponto decimal do arquivo do IBGE como separador de milhar (R2.3).
    idhm = relido[COLUNA_IDHM_2010].dropna()
    assert not idhm.empty, "o IDHM deveria ter sido anexado"
    assert (idhm > 0).all() and (idhm <= 1).all(), (
        f"IDHM fora da escala [0,1]: {sorted(idhm.unique())} — o separador "
        "decimal do arquivo de municípios foi destruído na conversão"
    )
    # O PIB per capita preserva a ordem de grandeza declarada no fixture.
    pib = relido[COLUNA_PIB_PER_CAPITA_2023].dropna()
    assert set(pib.round(2)) == {35000.00}

    # Renda e escolaridade estão materializadas para a dispersão do dashboard (R7.4).
    assert relido[COLUNA_SALARIO_MEDIO_ADMISSAO].notna().any()
    assert relido[COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO].notna().any()

    # --- Etapa 6: Upload para o Azure mockado (R9) --------------------------
    cliente_azure = ContainerFake()
    fabrica = FabricaFake(cliente_azure)
    enviados = upload_tabelas(
        str(destino_agregado),
        _CONTAINER,
        env={VAR_CREDENCIAL_AZURE: _CONN_VALIDA},
        client_factory=fabrica,
    )

    # O blob da tabela agregada foi enviado ao cliente Azure simulado (R9.1).
    assert enviados == ["caged_agregado.parquet"]
    assert fabrica.chamadas == 1
    assert len(cliente_azure.uploads) == 1
    nome, data, overwrite = cliente_azure.uploads[0]
    assert nome == "caged_agregado.parquet"
    assert data == destino_agregado.read_bytes()
    assert overwrite is True
