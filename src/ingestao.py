"""Ingestor do pipeline (R1): carga e validação dos arquivos de origem.

Este módulo é a fronteira de I/O da etapa de ingestão. As funções de leitura
(`ler_caged`, `ler_municipios`) isolam o acesso a disco e garantem que qualquer
arquivo ausente, inacessível ou ilegível resulte em um erro que *identifica o
arquivo* (R1.10), permitindo que o pipeline interrompa cedo e de forma explícita
sem persistir estado parcial (princípio de "falha explícita e cedo" do design).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.erros import ErroDeValidacao
from src.logging_pipeline import log_etapa

# Colunas de índice espúrias que o CAGED de origem carrega e devem ser
# descartadas na leitura (R1.3).
_COLUNAS_INDICE_DESCARTAR = ["Unnamed: 0.1", "Unnamed: 0"]

# Colunas obrigatórias do CAGED verificadas por `validar_colunas` (R1.6).
COLUNAS_OBRIGATORIAS_CAGED = [
    "competênciamov",
    "município",
    "seção",
    "subclasse",
    "saldomovimentação",
    "cbo2002ocupação",
    "graudeinstrução",
    "idade",
    "raçacor",
    "sexo",
    "salário",
    "valorsaláriofixo",
]


def _ler_csv_identificando_arquivo(caminho: str, **kwargs) -> pd.DataFrame:
    """Lê um CSV repassando `kwargs` ao pandas; em falha de I/O levanta
    `ErroDeValidacao` identificando o arquivo (R1.10).

    Captura os erros típicos de arquivo ausente/inacessível/ilegível
    (`FileNotFoundError`, `PermissionError`, `IsADirectoryError`, `OSError`) e
    de conteúdo não parseável (`pandas.errors.*`), reembalando-os numa exceção
    de validação cuja mensagem inclui o caminho do arquivo ofensor.
    """
    try:
        return pd.read_csv(caminho, **kwargs)
    except (FileNotFoundError, PermissionError, IsADirectoryError) as exc:
        raise ErroDeValidacao(
            f"Arquivo de origem ausente ou inacessível: {caminho!r} ({exc})"
        ) from exc
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise ErroDeValidacao(
            f"Arquivo de origem ilegível ou malformado: {caminho!r} ({exc})"
        ) from exc
    except OSError as exc:
        # Demais falhas de sistema de arquivos (ex.: erro de leitura de bloco).
        raise ErroDeValidacao(
            f"Falha ao ler o arquivo de origem: {caminho!r} ({exc})"
        ) from exc


def ler_caged(caminho: str) -> pd.DataFrame:
    """Lê o CAGED com `sep=';'`, `decimal=','`, encoding utf-8 (R1.1),
    descartando as colunas de índice `Unnamed: 0.1` e `Unnamed: 0` (R1.3).

    Em caso de arquivo ausente, inacessível ou ilegível, levanta
    `ErroDeValidacao` identificando o arquivo (R1.10).
    """
    df = _ler_csv_identificando_arquivo(
        caminho,
        sep=";",
        decimal=",",
        encoding="utf-8",
        dtype=str,
    )
    # Descarta as colunas de índice espúrias quando presentes (R1.3).
    colunas_para_remover = [c for c in _COLUNAS_INDICE_DESCARTAR if c in df.columns]
    if colunas_para_remover:
        df = df.drop(columns=colunas_para_remover)
    return df


def ler_municipios(caminho: str) -> pd.DataFrame:
    """Lê a Base_de_Municipios com `sep=','` (R1.2).

    Em caso de arquivo ausente, inacessível ou ilegível, levanta
    `ErroDeValidacao` identificando o arquivo (R1.10).
    """
    return _ler_csv_identificando_arquivo(caminho, sep=",", dtype=str)


# Valor único esperado na coluna `uf` do CAGED de Santa Catarina (R1.4).
UF_ESPERADA = 42


def validar_uf(df: pd.DataFrame) -> None:
    """Valida que a coluna `uf` contém exclusivamente o valor 42 (R1.4).

    A validação é aprovada se e somente se todas as linhas têm ``uf == 42``.
    Havendo qualquer divergência, levanta `ErroDeValidacao` reportando a
    quantidade exata de registros divergentes, interrompendo o processamento
    antes de qualquer persistência (R1.5).

    O valor da coluna é comparado de forma robusta a `uf` lida como texto
    (os leitores usam ``dtype=str``) ou como inteiro: cada valor é convertido
    para inteiro quando possível; valores não numéricos contam como divergentes.

    Args:
        df: DataFrame do CAGED carregado, contendo a coluna `uf`.

    Raises:
        ErroDeValidacao: se a coluna `uf` estiver ausente ou se houver ao menos
            um registro com ``uf != 42``.
    """
    if "uf" not in df.columns:
        raise ErroDeValidacao(
            "Coluna obrigatória ausente para validação de UF: 'uf'."
        )

    uf_numerica = pd.to_numeric(df["uf"], errors="coerce")
    # Valores não convertíveis (NaN) e diferentes de 42 são divergentes.
    divergentes = int((uf_numerica != UF_ESPERADA).sum())
    if divergentes > 0:
        raise ErroDeValidacao(
            f"Validação de UF falhou: {divergentes} registro(s) com "
            f"uf != {UF_ESPERADA}."
        )


def validar_colunas(df: pd.DataFrame) -> None:
    """Valida a presença das colunas obrigatórias do CAGED (R1.6).

    A validação é aprovada se e somente se todas as colunas de
    `COLUNAS_OBRIGATORIAS_CAGED` estão presentes. Havendo ausências, levanta
    `ErroDeValidacao` listando exatamente as colunas faltantes, preservando a
    ordem de `COLUNAS_OBRIGATORIAS_CAGED`, e interrompe o processamento sem
    persistir (R1.7).

    Args:
        df: DataFrame do CAGED carregado.

    Raises:
        ErroDeValidacao: se uma ou mais colunas obrigatórias estiverem ausentes.
    """
    presentes = set(df.columns)
    ausentes = [col for col in COLUNAS_OBRIGATORIAS_CAGED if col not in presentes]
    if ausentes:
        faltantes = ", ".join(repr(col) for col in ausentes)
        raise ErroDeValidacao(
            f"Colunas obrigatórias ausentes no CAGED: {faltantes}."
        )


@dataclass(frozen=True)
class IngestResult:
    """Resultado da ingestão (R1.9).

    Carrega a contagem exata de linhas lidas de cada arquivo de origem e o
    caminho do Parquet bruto persistido, para que o orquestrador (notebook)
    possa auditar a etapa e seguir para a limpeza.

    Attributes:
        linhas_caged: número de linhas de dados lidas do CAGED.
        linhas_municipios: número de linhas de dados lidas da Base_de_Municipios.
        destino_parquet: caminho do `caged_bruto.parquet` gravado.
    """

    linhas_caged: int
    linhas_municipios: int
    destino_parquet: str


def executar_ingestao(
    caminho_caged: str,
    caminho_municipios: str,
    destino_parquet: str,
) -> IngestResult:
    """Orquestra a etapa de ingestão do pipeline (R1).

    Fluxo, na ordem imposta pelo princípio de "falha explícita e cedo":

    1. Lê os dois arquivos de origem (R1.1, R1.2, R1.3); qualquer arquivo
       ausente/inacessível/ilegível levanta `ErroDeValidacao` identificando o
       arquivo (R1.10), antes de qualquer gravação.
    2. Valida o schema do CAGED: ``uf == 42`` em todas as linhas (R1.4/R1.5) e
       presença das colunas obrigatórias (R1.6/R1.7). Qualquer falha interrompe
       a execução *antes* de persistir.
    3. Somente após todas as validações passarem, persiste o conteúdo do CAGED
       em Parquet (R1.8).
    4. Registra a contagem exata de linhas lidas de cada arquivo (R1.9) e emite
       uma única mensagem de progresso para a etapa (R8.4).

    Args:
        caminho_caged: caminho do arquivo CAGED de origem.
        caminho_municipios: caminho da Base_de_Municipios de origem.
        destino_parquet: caminho onde gravar o `caged_bruto.parquet`.

    Returns:
        IngestResult com `linhas_caged`, `linhas_municipios` e `destino_parquet`.

    Raises:
        ErroDeValidacao: se um arquivo de origem for ilegível (R1.10) ou se o
            schema do CAGED falhar na validação de UF (R1.5) ou de colunas
            (R1.7). Nesses casos nada é persistido.
    """
    # 1. Leitura das fontes (erro identificável se ausente/ilegível — R1.10).
    df_caged = ler_caged(caminho_caged)
    df_municipios = ler_municipios(caminho_municipios)

    # Contagem exata de linhas lidas de cada arquivo (R1.9), capturada antes
    # de qualquer transformação posterior.
    linhas_caged = len(df_caged)
    linhas_municipios = len(df_municipios)

    # 2. Validações de schema — levantam ErroDeValidacao antes de persistir
    # (R1.4/R1.5, R1.6/R1.7). A ordem garante que nenhum Parquet é escrito se
    # qualquer validação falhar.
    validar_uf(df_caged)
    validar_colunas(df_caged)

    # 3. Persistência do Parquet bruto — só ocorre após todas as validações
    # passarem (R1.8).
    df_caged.to_parquet(destino_parquet, index=False)

    # 4. Mensagem única de progresso da etapa (R8.4, R1.9).
    log_etapa(
        "ingestão",
        f"{linhas_caged} linhas do CAGED e {linhas_municipios} de municípios "
        f"lidas; Parquet bruto gravado em {destino_parquet!r}.",
    )

    return IngestResult(
        linhas_caged=linhas_caged,
        linhas_municipios=linhas_municipios,
        destino_parquet=destino_parquet,
    )
