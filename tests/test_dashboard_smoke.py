"""Smoke test do dashboard v2 com `streamlit.testing.v1.AppTest`.

Cada página renderiza sem exceção sobre os artefatos reais de
`data_processed/`, com os filtros padrão e com um filtro que não casa nada.
A página é chamada direto (sem a fronteira de erro), para que uma falha
apareça como exceção no teste em vez de virar um aviso na tela.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

PAGINAS = ["panorama", "diagnostico", "causa_raiz", "ocupacoes", "recomendacoes", "ficha",
           "metodologia", "apresentacao"]


def _roteiro(pagina: str, vazio: bool, passo: int = 0) -> None:
    import importlib

    import streamlit as st

    from dashboard import comum as c

    art = c.carregar_artefatos(env={})
    meses = sorted(art.agregado["mes"].astype(str).unique())
    filtros = c.Filtros(meses=(meses[0], meses[-1]),
                        territorios=("Território inexistente",) if vazio else ())
    st.session_state["_paginas"] = {}
    st.session_state["passo"] = passo
    modulo = importlib.import_module(f"dashboard.paginas.{pagina}")
    modulo.render(c.montar_contexto(art, filtros))


@pytest.mark.parametrize("vazio", [False, True], ids=["padrao", "sem_dados"])
@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_renderiza_sem_excecao(pagina: str, vazio: bool) -> None:
    at = AppTest.from_function(_roteiro, kwargs={"pagina": pagina, "vazio": vazio}, default_timeout=120)
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]


@pytest.mark.parametrize("passo", range(5))
def test_modo_apresentacao_renderiza_os_cinco_passos(passo: int) -> None:
    at = AppTest.from_function(_roteiro, kwargs={"pagina": "apresentacao", "vazio": False, "passo": passo},
                               default_timeout=120)
    at.run()
    assert not at.exception, [e.message for e in at.exception]


def test_app_completo_abre_no_panorama_sem_erro() -> None:
    at = AppTest.from_file("../dashboard/app.py", default_timeout=120)
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert at.title[0].value == "Onde está o problema?"


def test_modo_apresentacao_exige_a_chave_quando_configurada() -> None:
    from dashboard.paginas.apresentacao import acesso_liberado

    assert acesso_liberado("", None)
    assert not acesso_liberado("segredo", None)
    assert not acesso_liberado("segredo", "errada")
    assert acesso_liberado("segredo", "segredo")
