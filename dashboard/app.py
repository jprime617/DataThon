"""Raio-X da Indústria SC — ponto de entrada do dashboard (Streamlit multipágina).

Narrativa: **localizar o problema → entender a causa raiz → decidir**. Este
arquivo só monta a casca: carrega os artefatos (Blob → cópia local, com
validação de schema), desenha os filtros globais na barra lateral — que
persistem entre as páginas —, prepara o contexto filtrado uma vez por execução
e entrega a navegação. Dados, métricas e tema vivem em `dashboard/comum.py`;
as figuras em `dashboard/figuras.py`; as frases em `dashboard/narrativa.py`;
cada página em `dashboard/paginas/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run dashboard/app.py` só põe `dashboard/` no sys.path; a raiz do
# projeto precisa entrar antes dos imports de `src` e `dashboard`.
_RAIZ_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_PROJETO))

import streamlit as st

from dashboard import comum as c
from dashboard.paginas import (
    apresentacao,
    causa_raiz,
    diagnostico,
    ficha,
    metodologia,
    ocupacoes,
    panorama,
    recomendacoes,
)

# (chave, módulo, título no menu, ícone Material, caminho na URL)
PAGINAS = [
    ("panorama", panorama, "Panorama", ":material/map:", "panorama"),
    ("diagnostico", diagnostico, "Diagnóstico", ":material/crisis_alert:", "diagnostico"),
    ("causa_raiz", causa_raiz, "Causa raiz", ":material/troubleshoot:", "causa-raiz"),
    ("ocupacoes", ocupacoes, "Ocupações (IA)", ":material/psychology:", "ocupacoes"),
    ("recomendacoes", recomendacoes, "Recomendações", ":material/lightbulb:", "recomendacoes"),
    ("ficha", ficha, "Ficha do território", ":material/location_city:", "ficha"),
    ("metodologia", metodologia, "Metodologia", ":material/menu_book:", "metodologia"),
    ("apresentacao", apresentacao, "Modo apresentação", ":material/slideshow:", "apresentacao"),
]


def main() -> None:
    st.set_page_config(page_title="Raio-X da Indústria SC", page_icon=":material/factory:", layout="wide")
    c.registrar_template()

    paginas = {
        chave: st.Page(c.pagina_segura(titulo, modulo.render), title=titulo, icon=icone, url_path=url,
                       default=chave == "panorama")
        for chave, modulo, titulo, icone, url in PAGINAS
    }
    st.session_state["_paginas"] = paginas

    art = c.carregar_artefatos_cache()
    if not art.disponivel:
        st.title("Raio-X da Indústria SC")
        st.error(f"{art.motivo} {' '.join(art.avisos)}", icon=":material/cloud_off:")
        return

    st.sidebar.markdown("## Raio-X da Indústria SC")
    st.sidebar.caption("Apagão de mão de obra e expansão na indústria catarinense — Novo CAGED.")
    filtros = c.barra_lateral(art.agregado)
    st.session_state["_ctx"] = c.montar_contexto_cache(art, filtros)

    navegacao = st.navigation({
        "Narrativa": [paginas[k] for k in ("panorama", "diagnostico", "causa_raiz", "ocupacoes", "recomendacoes")],
        "Aprofundar": [paginas[k] for k in ("ficha", "metodologia")],
        "Pitch": [paginas["apresentacao"]],
    })
    navegacao.run()


if __name__ == "__main__":
    main()
