"""Testes de smoke / checagens documentais (tarefa 14.2).

Validam que os artefatos de documentação e configuração do projeto atendem aos
requisitos:

- `requirements.txt` existe e fixa TODAS as dependências com versão exata (`==`),
  sem faixas (`>=`, `<=`, `~=`, `>`, `<`, `*`, ou intervalos separados por vírgula).
  (R8.2)
- `README.md` existe e contém as seções exigidas: pré-requisitos de ambiente,
  comandos de instalação de dependências, comandos de execução do pipeline e
  comando para iniciar o dashboard. (R8.8)
- README documenta as premissas obrigatórias: (a) exclusões já aplicadas na
  origem; (b) IDHM 2010 desatualizado; (c) agrupamento de CBOs fora do Azure /
  sem Azure OpenAI. (R8.3, R9.5)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
REQUIREMENTS = RAIZ / "requirements.txt"
README = RAIZ / "README.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _linhas_de_dependencia(texto: str) -> list[str]:
    """Retorna apenas as linhas que declaram dependências.

    Ignora linhas em branco, comentários (`#`) e diretivas de opção do pip
    (`-r`, `--hash`, etc.).
    """
    linhas = []
    for bruta in texto.splitlines():
        linha = bruta.strip()
        if not linha or linha.startswith("#") or linha.startswith("-"):
            continue
        # Descarta comentário inline.
        linha = linha.split("#", 1)[0].strip()
        if linha:
            linhas.append(linha)
    return linhas


def _ler_readme() -> str:
    return README.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# requirements.txt — versões exatas fixadas (R8.2)
# ---------------------------------------------------------------------------
def test_requirements_existe():
    assert REQUIREMENTS.is_file(), "requirements.txt deve existir na raiz do projeto"


def test_requirements_tem_dependencias():
    deps = _linhas_de_dependencia(REQUIREMENTS.read_text(encoding="utf-8"))
    assert deps, "requirements.txt deve declarar ao menos uma dependência"


# Operadores/tokens de faixa que NÃO podem aparecer numa dependência fixada.
_TOKENS_DE_FAIXA = (">=", "<=", "~=", "!=", ">", "<", "*")


def test_requirements_fixa_versoes_exatas():
    """Toda dependência usa exatamente um pin `==`, sem faixas (R8.2)."""
    deps = _linhas_de_dependencia(REQUIREMENTS.read_text(encoding="utf-8"))
    problemas: list[str] = []

    for dep in deps:
        # Deve conter exatamente um especificador `==`.
        if dep.count("==") != 1:
            problemas.append(f"{dep!r}: não usa um único pin '=='")
            continue

        # Não pode conter intervalos separados por vírgula (ex.: ">=1,<2").
        if "," in dep:
            problemas.append(f"{dep!r}: contém intervalo separado por vírgula")
            continue

        nome, _, versao = dep.partition("==")
        versao = versao.strip()

        # Nenhum token de faixa pode aparecer em qualquer parte da linha.
        for token in _TOKENS_DE_FAIXA:
            if token in dep:
                problemas.append(f"{dep!r}: contém operador de faixa {token!r}")
                break
        else:
            # Versão fixada deve ser concreta: começa com dígito e não tem curinga.
            if not versao or not re.match(r"^\d", versao):
                problemas.append(f"{dep!r}: versão fixada inválida ({versao!r})")

    assert not problemas, "Dependências não fixadas com versão exata:\n" + "\n".join(
        problemas
    )


# ---------------------------------------------------------------------------
# README.md — seções exigidas (R8.8)
# ---------------------------------------------------------------------------
def test_readme_existe():
    assert README.is_file(), "README.md deve existir na raiz do projeto"


def test_readme_tem_pre_requisitos_de_ambiente():
    texto = _ler_readme().lower()
    # Pré-requisitos de ambiente: versão do Python de referência.
    assert "pré-requisitos" in texto or "pre-requisitos" in texto
    assert "3.11.9" in texto, "README deve indicar a versão de Python de referência"


def test_readme_tem_comando_de_instalacao():
    texto = _ler_readme()
    assert re.search(
        r"pip\s+install\s+-r\s+requirements\.txt", texto
    ), "README deve conter o comando de instalação 'pip install -r requirements.txt'"


def test_readme_tem_comando_de_execucao_do_pipeline():
    texto = _ler_readme()
    assert re.search(
        r"notebooks/01_pipeline\.ipynb", texto
    ), "README deve referenciar a execução do pipeline via notebooks/01_pipeline.ipynb"


def test_readme_tem_comando_de_inicio_do_dashboard():
    texto = _ler_readme()
    assert re.search(
        r"streamlit\s+run\s+dashboard/app\.py", texto
    ), "README deve conter o comando 'streamlit run dashboard/app.py'"


# ---------------------------------------------------------------------------
# README.md — premissas documentadas (R8.3, R9.5)
# ---------------------------------------------------------------------------
def test_readme_documenta_exclusoes_na_origem():
    """Premissa (a): exclusões já aplicadas na origem (R8.3a)."""
    texto = _ler_readme().lower()
    assert "indicadordeexclusão" in texto or "indicadordeexclusao" in texto
    assert "competênciaexc" in texto or "competenciaexc" in texto
    assert "origem" in texto


def test_readme_documenta_idhm_2010_desatualizado():
    """Premissa (b): IDHM 2010 desatualizado (R8.3b)."""
    texto = _ler_readme().lower()
    assert "idhm" in texto
    assert "2010" in texto
    assert "desatualizad" in texto


def test_readme_documenta_cbo_fora_do_azure():
    """Premissa (c): agrupamento de CBOs fora do Azure, sem Azure OpenAI (R9.5)."""
    texto = _ler_readme().lower()
    assert "cbo" in texto
    assert "fora do azure" in texto
    assert "azure openai" in texto, (
        "README deve registrar que o Azure OpenAI não é utilizado"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
