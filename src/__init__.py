"""Pacote do pipeline Datathon CAGED SC.

Expõe utilitários compartilhados usados por todas as etapas do pipeline:
o logger de progresso por etapa e a exceção de validação comum.
"""

from src.erros import ErroDeValidacao
from src.logging_pipeline import log_etapa, obter_logger

__all__ = ["ErroDeValidacao", "log_etapa", "obter_logger"]
