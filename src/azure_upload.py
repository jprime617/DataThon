"""Upload das tabelas agregadas para o Azure Blob Storage (R9).

Última etapa do pipeline: somente as tabelas agregadas finais (saída do
Agregador, poucos MB) sobem para o Blob_Storage, de onde o dashboard as lê
(R9.1, R9.2). O agrupamento de CBOs via LLM e o restante do pipeline rodam
**fora** do Azure (R9.5).

A função de fronteira `upload_tabelas` concentra o efeito colateral de rede:

- Lê a credencial de acesso ao Azure (`AZURE_STORAGE_CONNECTION_STRING`) da
  variável de ambiente (R8.5b).
- **Falha explícita e cedo** (princípio do design): se a credencial estiver
  ausente, vazia ou inválida, interrompe *antes* de qualquer chamada ao Azure,
  levantando `ErroDeValidacao` — garantindo que nenhum dado parcial seja enviado
  ao Blob_Storage (R8.7, R9.3).
- Faz o upload das tabelas agregadas para o container informado (R9.1).

Para manter o módulo testável sem qualquer chamada de rede, o cliente de Blob é
injetável via o parâmetro `client_factory` (abstração `FabricaClienteBlob`): nos
testes um cliente simulado é injetado; em produção o padrão constrói um
`BlobServiceClient` a partir da connection string. A guarda de credencial é
sempre executada *antes* de acionar a fábrica, de modo que a validação não
dependa do SDK nem da rede.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.erros import ErroDeValidacao
from src.logging_pipeline import log_etapa, obter_logger

# Nome da variável de ambiente que guarda a credencial de acesso ao Azure
# (R8.5b). Uma connection string do Storage Account (Blob_Storage).
VAR_CREDENCIAL_AZURE = "AZURE_STORAGE_CONNECTION_STRING"

# Prefixo esperado de uma connection string do Azure Storage. Serve para uma
# checagem barata de validade de formato *antes* de tocar na rede (R9.3): uma
# string presente mas claramente malformada é rejeitada sem chamar o Azure.
_PREFIXO_CONNECTION_STRING = "DefaultEndpointsProtocol="

# Extensões das tabelas agregadas que sobem para o Blob_Storage (R9.1). O
# Agregador exporta em Parquet ou CSV (R6.3); ambas são elegíveis ao upload.
_EXTENSOES_TABELAS = (".parquet", ".csv")

# Nome da etapa usado nas mensagens de log do pipeline (R8.4).
_ETAPA = "upload"


@runtime_checkable
class ClienteContainer(Protocol):
    """Interface mínima de um cliente de container do Blob_Storage.

    Abstrai o `ContainerClient` do SDK `azure-storage-blob`, expondo apenas o
    necessário para enviar um blob. Permite injetar um cliente simulado nos
    testes sem qualquer chamada de rede.
    """

    def upload_blob(self, name: str, data: bytes, *, overwrite: bool = ...) -> object:
        """Envia `data` como um blob chamado `name` ao container.

        Args:
            name: nome do blob de destino (ex.: ``caged_agregado.parquet``).
            data: conteúdo binário do arquivo a enviar.
            overwrite: se ``True``, sobrescreve um blob existente de mesmo nome.

        Returns:
            Um identificador/handle do blob enviado (ignorado pelo pipeline).
        """
        ...


@runtime_checkable
class FabricaClienteBlob(Protocol):
    """Fábrica que constrói um `ClienteContainer` a partir da credencial (R9.1).

    A indireção isola `upload_tabelas` do SDK concreto do Azure: o padrão de
    produção constrói um `BlobServiceClient` da connection string e dele deriva o
    `ContainerClient`; os testes injetam uma fábrica que devolve um cliente
    simulado, sem rede.
    """

    def __call__(self, connection_string: str, container: str) -> ClienteContainer:
        """Cria o cliente do `container` autenticado por `connection_string`.

        Args:
            connection_string: credencial de acesso ao Azure (R8.5b).
            container: nome do container de destino no Blob_Storage.

        Returns:
            Um `ClienteContainer` pronto para receber uploads.
        """
        ...


def verificar_credencial_azure(
    env: "os._Environ[str] | dict[str, str] | None" = None,
) -> str:
    """Valida a credencial de acesso ao Azure antes de qualquer chamada de rede.

    Lê a variável de ambiente ``AZURE_STORAGE_CONNECTION_STRING`` (R8.5b) e
    interrompe a execução, levantando `ErroDeValidacao`, se ela estiver ausente,
    vazia ou claramente malformada (sem o prefixo esperado de uma connection
    string do Azure Storage). Garante que o pipeline falhe *antes* de enviar
    qualquer dado ao Blob_Storage (R8.7, R9.3).

    Args:
        env: mapeamento de variáveis de ambiente a consultar; usa
            ``os.environ`` quando omitido. Útil para testes.

    Returns:
        O valor da credencial (sem espaços ao redor).

    Raises:
        ErroDeValidacao: se a credencial estiver ausente, vazia ou inválida.
    """
    ambiente = os.environ if env is None else env
    credencial = (ambiente.get(VAR_CREDENCIAL_AZURE) or "").strip()
    if not credencial:
        raise ErroDeValidacao(
            f"Credencial de acesso ao Azure não fornecida: a variável de "
            f"ambiente {VAR_CREDENCIAL_AZURE!r} está ausente ou vazia. "
            f"Defina-a antes de executar o upload; nenhum dado foi enviado ao "
            f"Blob_Storage."
        )
    if _PREFIXO_CONNECTION_STRING not in credencial:
        raise ErroDeValidacao(
            f"Credencial de acesso ao Azure inválida: a variável de ambiente "
            f"{VAR_CREDENCIAL_AZURE!r} não parece uma connection string do "
            f"Azure Storage (esperado conter {_PREFIXO_CONNECTION_STRING!r}). "
            f"Corrija-a antes de executar o upload; nenhum dado foi enviado ao "
            f"Blob_Storage."
        )
    return credencial


def _fabrica_blob_padrao(connection_string: str, container: str) -> ClienteContainer:
    """Constrói o `ContainerClient` padrão a partir da connection string (R9.1).

    Importa o SDK ``azure-storage-blob`` de forma tardia (dentro da função) para
    que o módulo possa ser importado e testado — com fábrica injetada — mesmo em
    ambientes onde o SDK não esteja instalado.
    """
    from azure.storage.blob import BlobServiceClient

    servico = BlobServiceClient.from_connection_string(connection_string)
    return servico.get_container_client(container)


def _coletar_tabelas(caminho_local: str) -> list[Path]:
    """Lista as tabelas agregadas a enviar a partir de `caminho_local`.

    Aceita tanto um arquivo único (ex.: ``caged_agregado.parquet``) quanto um
    diretório, caso em que coleta todos os arquivos com extensão elegível
    (``.parquet``/``.csv``) em ordem determinística. Valida a existência da
    origem *antes* de qualquer upload, de modo coerente com a falha explícita e
    cedo (nenhum dado parcial — R9.3).

    Raises:
        ErroDeValidacao: se o caminho não existir ou se um diretório não contiver
            nenhuma tabela agregada elegível.
    """
    origem = Path(caminho_local)
    if not origem.exists():
        raise ErroDeValidacao(
            f"Tabelas agregadas não encontradas para upload: o caminho "
            f"{caminho_local!r} não existe. Nenhum dado foi enviado ao "
            f"Blob_Storage."
        )

    if origem.is_file():
        return [origem]

    tabelas = sorted(
        caminho
        for caminho in origem.iterdir()
        if caminho.is_file() and caminho.suffix.lower() in _EXTENSOES_TABELAS
    )
    if not tabelas:
        raise ErroDeValidacao(
            f"Nenhuma tabela agregada ({'/'.join(_EXTENSOES_TABELAS)}) "
            f"encontrada em {caminho_local!r} para upload. Nenhum dado foi "
            f"enviado ao Blob_Storage."
        )
    return tabelas


def upload_tabelas(
    caminho_local: str,
    container: str,
    *,
    env: "os._Environ[str] | dict[str, str] | None" = None,
    client_factory: FabricaClienteBlob | None = None,
) -> list[str]:
    """Envia as tabelas agregadas ao Blob_Storage com guarda de credencial (R9).

    Executa a última etapa do pipeline:

    1. Valida a credencial de acesso ao Azure *antes* de qualquer chamada de rede
       (`verificar_credencial_azure`), interrompendo com `ErroDeValidacao` se
       ausente/vazia/inválida — nenhum dado parcial é enviado (R8.7, R9.3).
    2. Coleta as tabelas agregadas em `caminho_local` (arquivo único ou todas as
       tabelas ``.parquet``/``.csv`` de um diretório), validando a existência da
       origem antes de enviar.
    3. Faz o upload de cada tabela ao `container` informado, sobrescrevendo blobs
       de mesmo nome (R9.1).

    O cliente de Blob é injetável via `client_factory` para isolar os testes de
    qualquer chamada de rede; quando omitido, o padrão constrói um
    `BlobServiceClient` a partir da connection string (SDK ``azure-storage-blob``).

    Args:
        caminho_local: caminho de um arquivo de tabela agregada ou de um
            diretório contendo-as (ex.: ``data_processed/caged_agregado.parquet``
            ou ``data_processed``).
        container: nome do container de destino no Blob_Storage.
        env: mapeamento de variáveis de ambiente para a guarda de credencial;
            usa ``os.environ`` quando omitido. Útil para testes.
        client_factory: fábrica que constrói o `ClienteContainer`; quando
            omitida, usa a fábrica padrão baseada no SDK do Azure. Injetável nos
            testes para evitar rede.

    Returns:
        A lista dos nomes de blob efetivamente enviados, na ordem de upload.

    Raises:
        ErroDeValidacao: se a credencial do Azure estiver ausente/vazia/inválida
            (R8.7, R9.3) ou se não houver tabelas a enviar em `caminho_local`.
    """
    logger = obter_logger()

    # 1. Guarda de credencial antes de qualquer chamada ao Azure (R8.7, R9.3).
    credencial = verificar_credencial_azure(env)

    # 2. Coleta as tabelas a enviar, validando a origem antes do upload (R9.3).
    tabelas = _coletar_tabelas(caminho_local)

    # 3. Constrói o cliente do container (SDK real ou injetado) e envia (R9.1).
    fabrica = client_factory or _fabrica_blob_padrao
    cliente = fabrica(credencial, container)

    enviados: list[str] = []
    for tabela in tabelas:
        nome_blob = tabela.name
        cliente.upload_blob(nome_blob, tabela.read_bytes(), overwrite=True)
        enviados.append(nome_blob)

    log_etapa(
        _ETAPA,
        (
            f"{len(enviados)} tabela(s) agregada(s) enviada(s) ao container "
            f"{container!r} do Blob_Storage: {enviados}."
        ),
        logger=logger,
    )
    return enviados


__all__ = [
    "VAR_CREDENCIAL_AZURE",
    "ClienteContainer",
    "FabricaClienteBlob",
    "verificar_credencial_azure",
    "upload_tabelas",
]
