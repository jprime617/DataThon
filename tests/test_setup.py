"""Testes de smoke da configuração do projeto (tarefa 1).

Verificam que os utilitários compartilhados importam, que a exceção de validação
se comporta como esperado, que o logger de progresso emite uma única mensagem por
etapa e que o perfil padrão do Hypothesis está ativo com 100 exemplos.
"""

from __future__ import annotations

import logging

from hypothesis import given, settings
from hypothesis import strategies as st

from src import ErroDeValidacao, log_etapa, obter_logger


def test_erro_de_validacao_e_excecao():
    assert issubclass(ErroDeValidacao, Exception)
    try:
        raise ErroDeValidacao("3 linhas com uf != 42")
    except ErroDeValidacao as exc:
        assert "uf != 42" in str(exc)


def test_logger_e_idempotente():
    logger1 = obter_logger()
    qtd_handlers = len(logger1.handlers)
    logger2 = obter_logger()
    # Chamar de novo não deve duplicar handlers (uma mensagem por etapa).
    assert len(logger2.handlers) == qtd_handlers
    assert logger1 is logger2


def test_log_etapa_emite_uma_mensagem(caplog):
    logger = obter_logger()
    with caplog.at_level(logging.INFO, logger=logger.name):
        log_etapa("ingestão", "3.400.000 linhas lidas")
    mensagens = [r for r in caplog.records if r.name == logger.name]
    assert len(mensagens) == 1
    assert "ingestão" in mensagens[0].getMessage()


def test_perfil_hypothesis_tem_100_exemplos():
    perfil = settings.get_profile("datathon")
    assert perfil.max_examples == 100


@given(st.integers())
@settings(max_examples=5)
def test_hypothesis_executa(n):
    # Smoke: o Hypothesis roda sob a configuração da suíte.
    assert isinstance(n, int)
