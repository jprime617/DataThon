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
    c.estilo_global()

    paginas = {
        chave: st.Page(c.pagina_segura(titulo, modulo.render), title=titulo, icon=icone, url_path=url,
                       default=chave == "panorama",
                       # Fora do menu: só quem tem a URL (e a chave, se configurada).
                       visibility="hidden" if chave == "apresentacao" else "visible")
        for chave, modulo, titulo, icone, url in PAGINAS
    }
    st.session_state["_paginas"] = paginas

    art = c.carregar_artefatos_cache()
    if not art.disponivel:
        st.title("Raio-X da Indústria SC")
        st.error(f"{art.motivo} {' '.join(art.avisos)}", icon=":material/cloud_off:")
        return

    # Menu próprio (lista plana sob o título); o nativo fica oculto, mas as
    # rotas — inclusive a do modo apresentação — continuam valendo.
    navegacao = st.navigation(list(paginas.values()), position="hidden")
    st.sidebar.html('<p class="rx-trilha">Santa Catarina /</p>'
                    '<p class="rx-titulo" role="heading" aria-level="2">Raio-X da Indústria SC</p>')
    st.sidebar.caption("Apagão de mão de obra e expansão na indústria catarinense — Novo CAGED.")
    for chave, *_ in PAGINAS:
        if chave != "apresentacao":
            st.sidebar.page_link(paginas[chave])
    # O link ativo não expõe aria-current; marca-o pelo href (a página padrão usa "").
    ativo = next((url for chave, _, _, _, url in PAGINAS if paginas[chave] is navegacao), None)
    if ativo:
        href = "" if ativo == "panorama" else ativo
        st.sidebar.html(f'<style>[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][href="{href}"]'
                        "{background:#17809A;font-weight:700}</style>")
    filtros = c.barra_lateral(art.agregado)
    st.session_state["_ctx"] = c.montar_contexto_cache(art, filtros)
    navegacao.run()


if __name__ == "__main__":
    main()
