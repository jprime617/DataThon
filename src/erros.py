"""Exceções compartilhadas do pipeline.

`ErroDeValidacao` é levantada pelas etapas de validação (schema de UF, colunas
obrigatórias, credenciais) sempre que uma pré-condição falha, de modo que o
pipeline interrompa *antes* de persistir estado parcial (princípio de "falha
explícita e cedo" do design).
"""

from __future__ import annotations


class ErroDeValidacao(Exception):
    """Erro levantado quando uma validação de integridade do pipeline falha.

    Usada por `ingestao.validar_uf`, `ingestao.validar_colunas` e pelas guardas
    de credencial. A mensagem deve identificar com precisão o que falhou
    (ex.: contagem de linhas divergentes, lista exata de colunas ausentes).
    """
