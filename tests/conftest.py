"""Configuração compartilhada da suíte de testes.

Responsabilidades:
- Garantir que a raiz do projeto esteja em `sys.path`, de modo que `import src.*`
  funcione independentemente do diretório de invocação do pytest.
- Registrar e carregar o perfil padrão do Hypothesis com `max_examples=100`,
  conforme exigido pelo design para os testes property-based (propriedades 1–28).
"""

from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import HealthCheck, settings

# Raiz do projeto (pasta que contém `src/` e `tests/`).
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

# Perfil padrão: mínimo de 100 exemplos por propriedade (design, Testing Strategy).
settings.register_profile(
    "datathon",
    max_examples=100,
    # As propriedades testam correção, não tempo: o 1º exemplo (pandas frio)
    # passava dos 200 ms padrão e virava FlakyFailure intermitente (prop26).
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("datathon")
