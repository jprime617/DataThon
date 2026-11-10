"""Logging de progresso por etapa do pipeline (base para R8.4).

O notebook orquestrador executa o pipeline ponta a ponta e deve registrar uma
mensagem de progresso **única por etapa** (ingestão, limpeza, junção, métricas,
CBO/LLM, agregação, upload). Este módulo centraliza a configuração do logger e
oferece o helper `log_etapa`, que emite exatamente uma linha padronizada por
etapa concluída.
"""

from __future__ import annotations

import logging

_NOME_LOGGER = "datathon.pipeline"
_FORMATO = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def obter_logger(nome: str = _NOME_LOGGER) -> logging.Logger:
    """Retorna o logger do pipeline, configurando-o uma única vez.

    Idempotente: chamadas repetidas não acrescentam handlers duplicados, de
    modo que cada etapa gere apenas uma linha de log.
    """
    logger = logging.getLogger(nome)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMATO))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # Evita propagar para o root logger e duplicar a mensagem.
        logger.propagate = False
    return logger


def log_etapa(etapa: str, mensagem: str = "", *, logger: logging.Logger | None = None) -> None:
    """Emite uma mensagem única de progresso para uma etapa do pipeline (R8.4).

    Args:
        etapa: nome curto da etapa (ex.: "ingestão", "limpeza", "upload").
        mensagem: detalhe opcional (ex.: contagem de linhas, artefato gerado).
        logger: logger a usar; se omitido, usa o logger padrão do pipeline.
    """
    log = logger or obter_logger()
    if mensagem:
        log.info("[%s] %s", etapa, mensagem)
    else:
        log.info("[%s]", etapa)
