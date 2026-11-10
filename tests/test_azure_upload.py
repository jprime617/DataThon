"""Testes de exemplo/integração do upload para o Blob_Storage (tarefa 11.2).

Cobrem o comportamento de `upload_tabelas` e `verificar_credencial_azure` com um
cliente de container simulado (`ContainerFake`), sem qualquer chamada de rede e
usando `tmp_path` para as tabelas agregadas locais:

- guarda de credencial: credencial ausente/vazia/apenas-espaços/inválida (sem o
  prefixo de connection string) interrompe a execução levantando
  `ErroDeValidacao` e NENHUM upload é tentado — `upload_blob` do cliente fake
  nunca é chamado e a própria fábrica de clientes não é acionada (R8.7, R9.3);
- upload bem-sucedido: com credencial válida, as tabelas agregadas são enviadas
  ao container e o fake registra os nomes/conteúdos esperados dos blobs (R9.1);
- origem ausente: arquivo/diretório local inexistente interrompe com
  `ErroDeValidacao` depois de a credencial ser validada, mas antes de qualquer
  upload — nenhum dado parcial (R9.3).

O Azure é sempre mockado por `ContainerFake` + `FabricaFake`; a credencial é
exercitada via dicionário de ambiente injetado (`env=`), sem alterar o ambiente
real do processo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.erros import ErroDeValidacao
from src.azure_upload import (
    VAR_CREDENCIAL_AZURE,
    upload_tabelas,
    verificar_credencial_azure,
)

# Connection string válida (contém o prefixo esperado) usada nos casos de
# sucesso; os valores são fictícios e não representam uma credencial real.
_CONN_VALIDA = (
    "DefaultEndpointsProtocol=https;AccountName=fake;"
    "AccountKey=Zm9vYmFy;EndpointSuffix=core.windows.net"
)

# Uma string presente, porém claramente malformada (sem o prefixo de connection
# string): deve ser rejeitada sem tocar na rede (R9.3).
_CONN_INVALIDA = "isto-nao-e-uma-connection-string"

_CONTAINER = "tabelas-agregadas"


class ContainerFake:
    """Cliente de container simulado: registra uploads sem rede.

    Cada chamada a `upload_blob` é guardada como `(name, data, overwrite)` em
    `uploads`, de modo que os testes verifiquem os nomes e conteúdos dos blobs
    efetivamente enviados — ou, no caso da guarda de credencial, que `uploads`
    permaneceu vazio porque o método nunca foi chamado.
    """

    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, bool]] = []

    def upload_blob(self, name: str, data: bytes, *, overwrite: bool = False) -> object:
        self.uploads.append((name, data, overwrite))
        return object()


class FabricaFake:
    """Fábrica de `ContainerContainer` simulada, sem rede.

    Devolve sempre o mesmo `ContainerFake`, registrando a connection string e o
    container recebidos. `chamadas` conta quantas vezes a fábrica foi acionada,
    permitindo afirmar que a guarda de credencial interrompe ANTES de construir
    qualquer cliente (R8.7).
    """

    def __init__(self, cliente: ContainerFake) -> None:
        self._cliente = cliente
        self.chamadas = 0
        self.connection_strings: list[str] = []
        self.containers: list[str] = []

    def __call__(self, connection_string: str, container: str) -> ContainerFake:
        self.chamadas += 1
        self.connection_strings.append(connection_string)
        self.containers.append(container)
        return self._cliente


# ---------------------------------------------------------------------------
# Guarda de credencial: `verificar_credencial_azure` (R8.7, R9.3).
# ---------------------------------------------------------------------------


def test_verificar_credencial_aprova_quando_presente_e_valida():
    env = {VAR_CREDENCIAL_AZURE: f"  {_CONN_VALIDA}  "}
    # Retorna a credencial sem espaços ao redor e não levanta.
    assert verificar_credencial_azure(env) == _CONN_VALIDA


def test_verificar_credencial_falha_quando_ausente():
    with pytest.raises(ErroDeValidacao) as exc:
        verificar_credencial_azure({})
    assert VAR_CREDENCIAL_AZURE in str(exc.value)


def test_verificar_credencial_falha_quando_vazia():
    with pytest.raises(ErroDeValidacao) as exc:
        verificar_credencial_azure({VAR_CREDENCIAL_AZURE: ""})
    assert VAR_CREDENCIAL_AZURE in str(exc.value)


def test_verificar_credencial_falha_quando_apenas_espacos():
    with pytest.raises(ErroDeValidacao):
        verificar_credencial_azure({VAR_CREDENCIAL_AZURE: "    "})


def test_verificar_credencial_falha_quando_invalida():
    # Presente, porém sem o prefixo de connection string -> inválida (R9.3).
    with pytest.raises(ErroDeValidacao) as exc:
        verificar_credencial_azure({VAR_CREDENCIAL_AZURE: _CONN_INVALIDA})
    assert VAR_CREDENCIAL_AZURE in str(exc.value)


def test_verificar_credencial_usa_env_var_do_processo(monkeypatch):
    # Sem `env` explícito, consulta `os.environ`; delenv garante ausência.
    monkeypatch.delenv(VAR_CREDENCIAL_AZURE, raising=False)
    with pytest.raises(ErroDeValidacao):
        verificar_credencial_azure()

    monkeypatch.setenv(VAR_CREDENCIAL_AZURE, _CONN_VALIDA)
    assert verificar_credencial_azure() == _CONN_VALIDA


# ---------------------------------------------------------------------------
# `upload_tabelas` interrompe sem enviar quando a credencial é inválida/ausente
# (R8.7, R9.3): a fábrica nunca é acionada e nenhum blob é enviado.
# ---------------------------------------------------------------------------


def _tabela_parquet(tmp_path: Path, nome: str = "caged_agregado.parquet") -> Path:
    """Cria um arquivo de tabela agregada fictício em `tmp_path`.

    O conteúdo é binário arbitrário: o upload apenas copia os bytes do arquivo
    para o blob, sem interpretar o formato, de modo que basta um placeholder.
    """
    caminho = tmp_path / nome
    caminho.write_bytes(b"conteudo-parquet-ficticio")
    return caminho


def test_upload_interrompe_sem_enviar_quando_credencial_ausente(tmp_path: Path):
    tabela = _tabela_parquet(tmp_path)
    cliente = ContainerFake()
    fabrica = FabricaFake(cliente)

    with pytest.raises(ErroDeValidacao) as exc:
        upload_tabelas(str(tabela), _CONTAINER, env={}, client_factory=fabrica)

    assert VAR_CREDENCIAL_AZURE in str(exc.value)
    # Interrompeu ANTES de construir o cliente e de enviar qualquer blob (R8.7).
    assert fabrica.chamadas == 0
    assert cliente.uploads == []


def test_upload_interrompe_sem_enviar_quando_credencial_vazia(tmp_path: Path):
    tabela = _tabela_parquet(tmp_path)
    cliente = ContainerFake()
    fabrica = FabricaFake(cliente)

    with pytest.raises(ErroDeValidacao):
        upload_tabelas(
            str(tabela),
            _CONTAINER,
            env={VAR_CREDENCIAL_AZURE: "   "},
            client_factory=fabrica,
        )

    assert fabrica.chamadas == 0
    assert cliente.uploads == []


def test_upload_interrompe_sem_enviar_quando_credencial_invalida(tmp_path: Path):
    # Credencial presente mas malformada -> rejeitada sem rede (R9.3).
    tabela = _tabela_parquet(tmp_path)
    cliente = ContainerFake()
    fabrica = FabricaFake(cliente)

    with pytest.raises(ErroDeValidacao):
        upload_tabelas(
            str(tabela),
            _CONTAINER,
            env={VAR_CREDENCIAL_AZURE: _CONN_INVALIDA},
            client_factory=fabrica,
        )

    assert fabrica.chamadas == 0
    assert cliente.uploads == []


# ---------------------------------------------------------------------------
# Upload bem-sucedido com mock (R9.1).
# ---------------------------------------------------------------------------


def test_upload_envia_arquivo_unico_para_o_container(tmp_path: Path):
    conteudo = b"bytes-da-tabela-agregada"
    tabela = tmp_path / "caged_agregado.parquet"
    tabela.write_bytes(conteudo)
    cliente = ContainerFake()
    fabrica = FabricaFake(cliente)

    enviados = upload_tabelas(
        str(tabela),
        _CONTAINER,
        env={VAR_CREDENCIAL_AZURE: _CONN_VALIDA},
        client_factory=fabrica,
    )

    # A fábrica foi acionada uma vez com a credencial e o container corretos.
    assert fabrica.chamadas == 1
    assert fabrica.connection_strings == [_CONN_VALIDA]
    assert fabrica.containers == [_CONTAINER]

    # O blob esperado foi enviado com nome, conteúdo e overwrite corretos (R9.1).
    assert enviados == ["caged_agregado.parquet"]
    assert len(cliente.uploads) == 1
    nome, data, overwrite = cliente.uploads[0]
    assert nome == "caged_agregado.parquet"
    assert data == conteudo
    assert overwrite is True


def test_upload_envia_todas_as_tabelas_de_um_diretorio(tmp_path: Path):
    # Diretório com duas tabelas elegíveis (.parquet e .csv) e um arquivo
    # não-elegível (.txt) que NÃO deve ser enviado.
    (tmp_path / "agregado_a.parquet").write_bytes(b"aaa")
    (tmp_path / "agregado_b.csv").write_bytes(b"bbb")
    (tmp_path / "leia-me.txt").write_bytes(b"ignorar")
    cliente = ContainerFake()
    fabrica = FabricaFake(cliente)

    enviados = upload_tabelas(
        str(tmp_path),
        _CONTAINER,
        env={VAR_CREDENCIAL_AZURE: _CONN_VALIDA},
        client_factory=fabrica,
    )

    # Apenas as duas tabelas elegíveis foram enviadas, em ordem determinística.
    assert enviados == ["agregado_a.parquet", "agregado_b.csv"]
    nomes_enviados = [nome for nome, _, _ in cliente.uploads]
    assert nomes_enviados == ["agregado_a.parquet", "agregado_b.csv"]
    assert "leia-me.txt" not in nomes_enviados

    # Conteúdos preservados por blob.
    por_nome = {nome: data for nome, data, _ in cliente.uploads}
    assert por_nome["agregado_a.parquet"] == b"aaa"
    assert por_nome["agregado_b.csv"] == b"bbb"


def test_upload_usa_env_var_do_processo_quando_env_omitido(tmp_path: Path, monkeypatch):
    tabela = _tabela_parquet(tmp_path)
    cliente = ContainerFake()
    fabrica = FabricaFake(cliente)
    monkeypatch.setenv(VAR_CREDENCIAL_AZURE, _CONN_VALIDA)

    enviados = upload_tabelas(str(tabela), _CONTAINER, client_factory=fabrica)

    assert enviados == ["caged_agregado.parquet"]
    assert fabrica.chamadas == 1


# ---------------------------------------------------------------------------
# Origem local ausente: interrompe após validar a credencial, sem enviar (R9.3).
# ---------------------------------------------------------------------------


def test_upload_arquivo_local_ausente_levanta_erro_sem_enviar(tmp_path: Path):
    inexistente = tmp_path / "nao_existe.parquet"
    cliente = ContainerFake()
    fabrica = FabricaFake(cliente)

    with pytest.raises(ErroDeValidacao) as exc:
        upload_tabelas(
            str(inexistente),
            _CONTAINER,
            env={VAR_CREDENCIAL_AZURE: _CONN_VALIDA},
            client_factory=fabrica,
        )

    assert "nao_existe.parquet" in str(exc.value)
    # Credencial válida: a fábrica chega a ser construída, mas nenhum blob é
    # enviado porque a origem não existe (nenhum dado parcial — R9.3).
    assert cliente.uploads == []


def test_upload_diretorio_sem_tabelas_levanta_erro_sem_enviar(tmp_path: Path):
    # Diretório existente, porém sem nenhuma tabela elegível (.parquet/.csv).
    vazio = tmp_path / "sem_tabelas"
    vazio.mkdir()
    (vazio / "notas.txt").write_bytes(b"nada elegivel")
    cliente = ContainerFake()
    fabrica = FabricaFake(cliente)

    with pytest.raises(ErroDeValidacao) as exc:
        upload_tabelas(
            str(vazio),
            _CONTAINER,
            env={VAR_CREDENCIAL_AZURE: _CONN_VALIDA},
            client_factory=fabrica,
        )

    assert "sem_tabelas" in str(exc.value)
    assert cliente.uploads == []
