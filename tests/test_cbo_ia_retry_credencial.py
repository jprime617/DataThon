"""Testes de exemplo do fluxo de retry e da guarda de credencial (tarefa 8.4).

Cobrem o comportamento de `classificar_lote`, `verificar_credencial_llm` e
`classificar_cbos` com um cliente LLM simulado (sem rede), validando:

- retry em até 3 tentativas quando a requisição falha/estoura o tempo, com
  sucesso numa tentativa intermediária devolvendo o mapeamento validado (R5.7);
- esgotadas as 3 tentativas, todo o lote recebe `Não classificado` (R5.7);
- macrofamília fora do conjunto `MACROFAMILIAS` ou ausente na resposta →
  `Não classificado` (R5.6, relacionado a R5.7);
- guarda de credencial: `verificar_credencial_llm` interrompe (levanta
  `ErroDeValidacao`) quando `LLM_API_KEY` está ausente ou vazia, e
  `classificar_cbos` interrompe ANTES de chamar a API externa nesse caso (R8.6).

O LLM é sempre mockado por `ClienteFake`, de modo que nenhum teste faça chamada
de rede. A guarda de credencial é exercitada via dicionário de ambiente injetado
(`env=`), sem alterar o ambiente real do processo.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src import ErroDeValidacao
from src.cbo_ia import (
    COLUNA_CBO,
    MAX_TENTATIVAS,
    NAO_CLASSIFICADO,
    TIMEOUT_SEGUNDOS,
    VAR_CREDENCIAL_LLM,
    classificar_cbos,
    classificar_lote,
    criar_cliente_llm,
    ClienteLLM,
    VAR_PROVEDOR_LLM,
    verificar_credencial_llm,
)
from src.mapeamentos import MACROFAMILIAS

# Uma macrofamília válida qualquer (não o fallback) para as respostas simuladas.
_FAMILIA_VALIDA = next(f for f in MACROFAMILIAS if f != NAO_CLASSIFICADO)


class ClienteFake:
    """Cliente LLM simulado, configurável por tentativa e sem chamada de rede.

    `respostas` é a sequência de resultados por chamada a `classificar`: cada
    item é ou uma `str` (resposta textual do modelo, devolvida) ou uma instância
    de `Exception` (levantada, simulando falha/timeout). Registra os `timeout`
    recebidos e conta as chamadas efetuadas, para que os testes verifiquem o
    número de tentativas e o timeout aplicado.
    """

    def __init__(self, respostas: list[object]):
        self._respostas = list(respostas)
        self.chamadas = 0
        self.timeouts: list[int] = []
        self.prompts: list[str] = []

    def classificar(self, prompt: str, *, timeout: int) -> str:
        self.chamadas += 1
        self.timeouts.append(timeout)
        self.prompts.append(prompt)
        indice = self.chamadas - 1
        if indice >= len(self._respostas):
            # Por padrão, chamadas além do roteiro falham (defensivo).
            raise TimeoutError("sem resposta configurada para esta tentativa")
        resultado = self._respostas[indice]
        if isinstance(resultado, Exception):
            raise resultado
        return str(resultado)


def _resposta_json(mapa: dict[str, str]) -> str:
    """Resposta textual do modelo: `{cbo: {macrofamilia, justificativa}}`."""
    return json.dumps({k: {"macrofamilia": v, "justificativa": "teste"} for k, v in mapa.items()})


def _familias(resultado: dict[str, dict]) -> dict[str, str]:
    """Só a macrofamília de cada código do resultado de `classificar_lote`."""
    return {k: v["macrofamilia"] for k, v in resultado.items()}


# ---------------------------------------------------------------------------
# Retry de `classificar_lote` (R5.7).
# ---------------------------------------------------------------------------


def test_retry_sucesso_na_terceira_tentativa_retorna_mapeamento():
    # Duas falhas (falha genérica + timeout) seguidas de sucesso na 3ª tentativa.
    lote = ["111", "222"]
    sucesso = _resposta_json({"111": _FAMILIA_VALIDA, "222": _FAMILIA_VALIDA})
    client = ClienteFake(
        [
            RuntimeError("falha de rede"),
            TimeoutError("estouro de tempo"),
            sucesso,
        ]
    )

    resultado = classificar_lote(lote, client)

    # Tentou 3 vezes (2 falhas + 1 sucesso) e devolveu o mapeamento validado.
    assert client.chamadas == 3
    assert _familias(resultado) == {"111": _FAMILIA_VALIDA, "222": _FAMILIA_VALIDA}
    # O timeout por requisição é o configurado (60 s).
    assert client.timeouts == [TIMEOUT_SEGUNDOS] * 3


def test_retry_sucesso_na_segunda_tentativa_nao_chama_terceira():
    # Falha na 1ª e sucesso na 2ª: não deve haver 3ª chamada.
    lote = ["333"]
    sucesso = _resposta_json({"333": _FAMILIA_VALIDA})
    client = ClienteFake([TimeoutError("timeout"), sucesso])

    resultado = classificar_lote(lote, client)

    assert client.chamadas == 2
    assert _familias(resultado) == {"333": _FAMILIA_VALIDA}


def test_retry_esgotado_atribui_nao_classificado_a_todo_o_lote():
    # Três falhas consecutivas: esgotadas as tentativas, todo o lote → fallback.
    lote = ["444", "555", "666"]
    client = ClienteFake(
        [
            TimeoutError("timeout 1"),
            RuntimeError("falha 2"),
            TimeoutError("timeout 3"),
        ]
    )

    resultado = classificar_lote(lote, client)

    # Tentou exatamente MAX_TENTATIVAS vezes e não excedeu.
    assert client.chamadas == MAX_TENTATIVAS == 3
    # Todo código do lote recebeu `Não classificado`.
    assert _familias(resultado) == {codigo: NAO_CLASSIFICADO for codigo in lote}


def test_lote_vazio_nao_chama_cliente():
    client = ClienteFake([])
    resultado = classificar_lote([], client)
    assert _familias(resultado) == {}
    assert client.chamadas == 0


# ---------------------------------------------------------------------------
# Fallback por macrofamília inválida/ausente (R5.6).
# ---------------------------------------------------------------------------


def test_macrofamilia_fora_do_conjunto_vira_nao_classificado():
    lote = ["777"]
    client = ClienteFake([_resposta_json({"777": "Macrofamília Inexistente"})])

    resultado = classificar_lote(lote, client)

    assert client.chamadas == 1
    assert _familias(resultado) == {"777": NAO_CLASSIFICADO}


def test_codigo_ausente_na_resposta_vira_nao_classificado():
    # A resposta classifica apenas um dos dois códigos; o outro → fallback.
    lote = ["888", "999"]
    client = ClienteFake([_resposta_json({"888": _FAMILIA_VALIDA})])

    resultado = classificar_lote(lote, client)

    assert client.chamadas == 1
    assert _familias(resultado) == {"888": _FAMILIA_VALIDA, "999": NAO_CLASSIFICADO}


def test_resposta_sem_json_valido_vira_nao_classificado():
    # Resposta sem objeto JSON: é uma resposta (não falha) → sem retry, fallback.
    lote = ["101"]
    client = ClienteFake(["desculpe, não consegui classificar"])

    resultado = classificar_lote(lote, client)

    assert client.chamadas == 1
    assert _familias(resultado) == {"101": NAO_CLASSIFICADO}


# ---------------------------------------------------------------------------
# Guarda de credencial: `verificar_credencial_llm` (R8.6).
# ---------------------------------------------------------------------------


def test_verificar_credencial_aprova_quando_presente():
    env = {VAR_CREDENCIAL_LLM: "  chave-secreta  "}
    # Retorna a credencial sem espaços ao redor e não levanta.
    assert verificar_credencial_llm(env) == "chave-secreta"


def test_verificar_credencial_falha_quando_ausente():
    with pytest.raises(ErroDeValidacao) as exc:
        verificar_credencial_llm({})
    assert VAR_CREDENCIAL_LLM in str(exc.value)


def test_verificar_credencial_falha_quando_vazia():
    with pytest.raises(ErroDeValidacao) as exc:
        verificar_credencial_llm({VAR_CREDENCIAL_LLM: ""})
    assert VAR_CREDENCIAL_LLM in str(exc.value)


def test_verificar_credencial_falha_quando_apenas_espacos():
    with pytest.raises(ErroDeValidacao):
        verificar_credencial_llm({VAR_CREDENCIAL_LLM: "    "})


def test_verificar_credencial_usa_env_var_do_processo(monkeypatch):
    # Sem `env` explícito, consulta `os.environ`; delvar garante ausência.
    monkeypatch.delenv(VAR_CREDENCIAL_LLM, raising=False)
    with pytest.raises(ErroDeValidacao):
        verificar_credencial_llm()

    monkeypatch.setenv(VAR_CREDENCIAL_LLM, "chave-do-processo")
    assert verificar_credencial_llm() == "chave-do-processo"


# ---------------------------------------------------------------------------
# Guarda de credencial em `classificar_cbos`: interrompe ANTES da API (R8.6).
# ---------------------------------------------------------------------------


def _df_caged_minimo() -> pd.DataFrame:
    """DataFrame CAGED-like mínimo com a coluna de código de ocupação."""
    return pd.DataFrame({COLUNA_CBO: ["223505", "317210"]})


def test_classificar_cbos_interrompe_sem_chamar_api_quando_credencial_ausente():
    df = _df_caged_minimo()
    client = ClienteFake([])  # qualquer chamada contaria em `client.chamadas`.

    with pytest.raises(ErroDeValidacao) as exc:
        classificar_cbos(df, client, env={})

    # Interrompeu antes de qualquer chamada ao LLM_Externo (R8.6).
    assert client.chamadas == 0
    assert VAR_CREDENCIAL_LLM in str(exc.value)


def test_classificar_cbos_interrompe_quando_credencial_vazia():
    df = _df_caged_minimo()
    client = ClienteFake([])

    with pytest.raises(ErroDeValidacao):
        classificar_cbos(df, client, env={VAR_CREDENCIAL_LLM: "   "})

    assert client.chamadas == 0


def test_classificar_cbos_prossegue_quando_credencial_presente(tmp_path):
    df = _df_caged_minimo()
    # Sucesso na 1ª chamada classificando os dois códigos distintos.
    resposta = _resposta_json({"223505": _FAMILIA_VALIDA, "317210": _FAMILIA_VALIDA})
    client = ClienteFake([resposta, resposta])  # rodadas 1 e 2
    destino = tmp_path / "cbo_macrofamilias.csv"

    resultado = classificar_cbos(
        df,
        client,
        destino_csv=str(destino),
        env={VAR_CREDENCIAL_LLM: "chave-valida"},
    )

    # Credencial presente: a guarda não interrompe e a API é chamada uma vez
    # por rodada.
    assert client.chamadas == 2
    assert resultado.mapeamento == {
        "223505": _FAMILIA_VALIDA,
        "317210": _FAMILIA_VALIDA,
    }


# ---------------------------------------------------------------------------
# Falhas permanentes: configuração, não transitório (extensão de R5.7/R8.6)
# ---------------------------------------------------------------------------


class _ErroHTTP(Exception):
    """Exceção com `status_code`, no formato dos SDKs HTTP (duck typing)."""

    def __init__(self, status_code: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status_code = status_code


class _ClienteQueFalhaComStatus:
    """Cliente que sempre falha com um status HTTP dado, contando as chamadas."""

    def __init__(self, status_code: int, mensagem: str = "recusado") -> None:
        self._erro = _ErroHTTP(status_code, mensagem)
        self.chamadas = 0

    def classificar(self, prompt: str, *, timeout: int) -> str:
        self.chamadas += 1
        raise self._erro


@pytest.mark.parametrize(
    ("status", "motivo"),
    [
        (400, "Your credit balance is too low to access the Anthropic API"),
        (401, "invalid x-api-key"),
        (403, "permission denied"),
        (404, "model not found"),
    ],
)
def test_falha_permanente_interrompe_sem_retry_nem_fallback(status, motivo):
    """Erro de configuração para o pipeline em vez de virar `Não classificado`.

    Saldo insuficiente, credencial inválida, falta de permissão e modelo
    inexistente não melhoram na terceira tentativa. Mascará-los com o fallback
    produziria um `cbo_macrofamilias.csv` inteiro de `Não classificado` sem que
    nada no pipeline falhasse — foi exatamente o que aconteceu em produção.
    """
    cliente = _ClienteQueFalhaComStatus(status, motivo)

    with pytest.raises(ErroDeValidacao) as excecao:
        classificar_lote(["715505", "223505"], cliente)

    # Uma única chamada: não há retry para falha permanente.
    assert cliente.chamadas == 1
    mensagem = str(excecao.value)
    assert str(status) in mensagem
    assert motivo in mensagem
    # A mensagem precisa dizer o que verificar.
    assert "LLM_API_KEY" in mensagem


def test_falha_transitoria_continua_com_retry_e_fallback():
    """Status transitório (5xx) preserva o comportamento de R5.7: 3 tentativas."""
    cliente = _ClienteQueFalhaComStatus(503, "service unavailable")

    resultado = classificar_lote(["715505", "223505"], cliente)

    assert cliente.chamadas == MAX_TENTATIVAS
    assert _familias(resultado) == {
        "715505": NAO_CLASSIFICADO,
        "223505": NAO_CLASSIFICADO,
    }


def test_falha_sem_status_code_continua_com_retry_e_fallback():
    """Exceção sem `status_code` (ex.: timeout de socket) segue o caminho de R5.7."""

    class ClienteQueEstoura:
        def __init__(self) -> None:
            self.chamadas = 0

        def classificar(self, prompt: str, *, timeout: int) -> str:
            self.chamadas += 1
            raise TimeoutError("estourou o tempo limite")

    cliente = ClienteQueEstoura()
    resultado = classificar_lote(["715505"], cliente)

    assert cliente.chamadas == MAX_TENTATIVAS
    assert _familias(resultado) == {"715505": NAO_CLASSIFICADO}


# ---------------------------------------------------------------------------
# Seleção de provedor do LLM_Externo (R5.9)
# ---------------------------------------------------------------------------


def test_criar_cliente_llm_usa_gemini_por_padrao():
    """Sem `LLM_PROVIDER`, o provedor é o Gemini — o caminho gratuito."""
    cliente = criar_cliente_llm(env={"LLM_API_KEY": "AIza-fake"})
    assert type(cliente).__name__ == "ClienteGemini"


def test_criar_cliente_llm_respeita_o_provedor_configurado():
    cliente = criar_cliente_llm(
        env={"LLM_API_KEY": "sk-ant-fake", VAR_PROVEDOR_LLM: "anthropic"}
    )
    assert type(cliente).__name__ == "ClienteClaude"


def test_criar_cliente_llm_aplica_a_guarda_de_credencial():
    """Credencial ausente interrompe antes de construir qualquer cliente (R8.6)."""
    with pytest.raises(ErroDeValidacao, match="LLM_API_KEY"):
        criar_cliente_llm(env={})


def test_criar_cliente_llm_rejeita_provedor_desconhecido():
    with pytest.raises(ErroDeValidacao, match="desconhecido"):
        criar_cliente_llm(env={"LLM_API_KEY": "x", VAR_PROVEDOR_LLM: "inexistente"})


def test_clientes_implementam_a_interface_cliente_llm():
    """Ambos os adaptadores satisfazem o Protocol usado por `classificar_lote`."""
    assert isinstance(criar_cliente_llm(env={"LLM_API_KEY": "x"}), ClienteLLM)
    assert isinstance(
        criar_cliente_llm(env={"LLM_API_KEY": "x", VAR_PROVEDOR_LLM: "anthropic"}),
        ClienteLLM,
    )
