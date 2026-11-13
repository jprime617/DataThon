"""1. Panorama — "Onde está o problema?"."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar
from dashboard.paginas.recomendacoes import POR_QUE_ALAVANCA

METRICAS_MAPA = [c.M_SALDO_10K, c.M_ROT_DESC, c.M_SAIDA_VOL, c.M_GAP_SAL]


def metricas_mapa(df: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """Métricas da unidade territorial, replicadas em cada município dela."""
    coluna = c.COLUNA_POR_NIVEL_TERRITORIAL[nivel]
    municipios = df[[c.COLUNA_MUNICIPIO, c.COLUNA_NOME_MUNICIPIO, c.COLUNA_REGIAO,
                     c.COLUNA_MICRORREGIAO]].drop_duplicates(c.COLUNA_MUNICIPIO).astype(str)
    por = c.agregar_metricas(df, [coluna])
    por[coluna] = por[coluna].astype(str)
    mapa = municipios.merge(por, on=coluna, how="left")
    mapa["rotulo"] = mapa[coluna]
    return mapa


def ranking_secoes(df: pd.DataFrame) -> pd.DataFrame:
    """R7.3: seções por saldo (decrescente), com a rotatividade descontada ao lado."""
    por = c.agregar_metricas(df, [c.COLUNA_SECAO_INDUSTRIAL])
    por = por[por[c.M_MOV] > 0].sort_values(c.M_SALDO, ascending=False, kind="stable")
    return pd.DataFrame({
        "Seção (CNAE)": por[c.COLUNA_SECAO_INDUSTRIAL].astype(str).values,
        "Saldo de vagas": por[c.M_SALDO].astype("int64").values,
        "Rotatividade descontada": por[c.M_ROT_DESC].where(por[c.M_AMOSTRA_OK]).values,
        "Saída voluntária": por[c.M_SAIDA_VOL].where(por[c.M_AMOSTRA_OK]).values,
        "Movimentações": por[c.M_MOV].astype("int64").values,
    })


def aplicar_achado(filtros: dict) -> None:
    """Aplica os filtros que provam um achado (callback de botão)."""
    for chave in _CHAVES_ACHADO:
        st.session_state[chave] = []
    st.session_state.update(filtros)


_CHAVES_ACHADO = ("f_terr", "f_setor", "f_macro", "f_niv")


def achado_ativo(filtros: dict, estado) -> bool:
    """O recorte atual é exatamente o que o achado aplica?"""
    if "f_nivel" in filtros and estado.get("f_nivel") != filtros["f_nivel"]:
        return False
    return all(list(estado.get(k) or []) == list(filtros.get(k, [])) for k in _CHAVES_ACHADO)


def volume_por_municipio(df: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """Movimentações de cada município (segunda camada do mapa), com o rótulo da unidade pintada."""
    coluna = c.COLUNA_POR_NIVEL_TERRITORIAL[nivel]
    por = c.agregar_metricas(df, list(dict.fromkeys([c.COLUNA_MUNICIPIO, c.COLUNA_NOME_MUNICIPIO, coluna])))
    return pd.DataFrame({
        c.COLUNA_MUNICIPIO: por[c.COLUNA_MUNICIPIO].astype(str),
        c.COLUNA_NOME_MUNICIPIO: por[c.COLUNA_NOME_MUNICIPIO].astype(str),
        "rotulo": por[coluna].astype(str),
        c.M_MOV: por[c.M_MOV],
    })


# --- Mapa: clicar seleciona; a ficha abre por um botão -----------------------------
# Antes o clique abria a ficha direto, e soltar o mouse depois de arrastar o
# mapa contava como clique. Agora o clique só escolhe o território, que ganha
# contorno e um cartão ao lado com o botão "Abrir a ficha".


def alvo_da_selecao(estado) -> str | None:
    """Rótulo do território clicado no estado do `st.plotly_chart` (dict ou atributos)."""
    if not estado:
        return None
    selecao = estado.get("selection") if isinstance(estado, dict) else getattr(estado, "selection", None)
    if not selecao:
        return None
    pontos = selecao.get("points") if isinstance(selecao, dict) else getattr(selecao, "points", None)
    for ponto in pontos or []:
        alvo = ponto.get("customdata")
        alvo = alvo[0] if isinstance(alvo, (list, tuple)) else alvo
        if alvo:
            return str(alvo)
    return None


def atualizar_selecao(estado_mapa, nivel: str, sessao) -> None:
    """Registra um clique novo; o mesmo clique repetido nos reruns não ressuscita uma seleção limpa."""
    alvo = alvo_da_selecao(estado_mapa)
    if alvo != sessao.get("_mapa_ultimo_clique"):
        sessao["_mapa_ultimo_clique"] = alvo
        if alvo:
            sessao["mapa_sel"] = (nivel, alvo)


def _limpar_selecao() -> None:
    st.session_state["mapa_sel"] = None


def _regua(pos: int, n: int, plural: str) -> str:
    """Régua "menor → maior" com a posição do território."""
    x = 100.0 if n == 1 else (n - pos) / (n - 1) * 100
    return (f'<div class="rx-regua" role="img" aria-label="{pos}º maior valor entre {n} {plural}">'
            '<div class="rx-extremos" aria-hidden="true"><span>menor</span><span>maior</span></div>'
            f'<div class="rx-trilho" aria-hidden="true"><span class="rx-marca" style="left:{x:.1f}%">'
            f'<em>{pos}º</em></span></div></div>')


def _cartao_selecao(ctx: c.Contexto, unidades: pd.DataFrame, metrica: str, nivel: str, alvo: str | None) -> None:
    plural = c.PLURAL_NIVEL[nivel]
    if not alvo:
        st.html('<div class="rx-painel"><p class="rx-l-titulo">Território</p>'
                f'<p class="rx-l-sub">Clique num território do mapa para ver aqui os números dele e abrir a '
                f'ficha completa. O mapa está pintado por {html.escape(nivel.lower())}.</p></div>')
        return
    linha = unidades[unidades["rotulo"] == alvo]
    if linha.empty:
        return
    u = linha.iloc[0]
    definicao = c.DEFINICOES[metrica]
    estado = c.total(ctx.df)[metrica]
    partes = ['<div class="rx-painel"><p class="rx-l-titulo">Território selecionado</p>',
              f'<div class="rx-sel-nome">{html.escape(alvo)}</div>']
    if u[c.M_AMOSTRA_OK] and pd.notna(u[metrica]):
        partes += [f'<div class="rx-sel-valor">{html.escape(c.fmt_metrica(metrica, u[metrica]))} '
                   f'<span>{html.escape(definicao.rotulo.lower())}</span></div>',
                   f'<div class="rx-sel-ref">Santa Catarina: {html.escape(c.fmt_metrica(metrica, estado))} · '
                   f'{c.fmt_int(u[c.M_MOV])} movimentações</div>']
        rank = c.posicao_ranking(unidades, "rotulo", metrica, alvo)
        if rank:
            partes.append(_regua(*rank, plural))
    else:
        partes.append(f'<p class="rx-l-sub">Poucos dados ({c.fmt_int(u[c.M_MOV])} movimentações, menos de '
                      f'{c.MIN_MOVIMENTACOES}): sem valor confiável para este indicador.</p>')
    st.html("".join(partes) + "</div>")
    if st.button(f"Abrir a ficha de {alvo}", key="mapa_abrir_ficha", type="primary",
                 icon=":material/location_city:", width="stretch"):
        st.session_state["ficha_alvo"] = (nivel, alvo)
        st.switch_page(st.session_state["_paginas"]["ficha"])
    st.button("Limpar seleção", key="mapa_limpar", icon=":material/close:", on_click=_limpar_selecao,
              type="tertiary")


def _legenda(unidades: pd.DataFrame, metrica: str, nivel: str, bolhas: bool) -> None:
    """Legenda em lista: polo de cima, faixas recuadas (com quantas unidades em cada), polo de baixo."""
    alto, baixo = nar.POLOS_MAPA.get(metrica, ("Maior valor", "Menor valor"))
    itens = fig.faixas_legenda(unidades, metrica, "rotulo")
    plural = c.PLURAL_NIVEL[nivel]
    linhas = "".join(f'<li><span class="rx-sw" style="background:{cor}"></span><span>{html.escape(faixa)}</span>'
                     f'<span class="rx-l-n">{n} {plural if n != 1 else nivel.lower()}</span></li>'
                     for cor, faixa, n in itens)
    poucos = int((~unidades[c.M_AMOSTRA_OK]).sum())
    extras = [f'<li><span class="rx-sw" style="background:{fig.COR_SEM_DADO}"></span>'
              f'<span>Poucos dados (menos de {c.MIN_MOVIMENTACOES} movimentações)'
              + (f' · {poucos}' if poucos else '') + '</span></li>',
              '<li><span class="rx-sw rx-sw-realce"></span><span>Território selecionado ou filtrado</span></li>']
    if bolhas:
        extras.append('<li><span class="rx-sw rx-sw-bolha"></span>'
                      '<span>Círculo: quanto maior, mais movimentações no município</span></li>')
    st.html('<div class="rx-painel"><p class="rx-l-titulo">Como ler as cores</p>'
            f'<p class="rx-l-sub">{html.escape(nar.UNIDADE_LEGENDA.get(metrica, ""))}</p>'
            f'<div class="rx-l-polo">▲ {html.escape(alto)}</div>'
            f'<ul class="rx-l-lista">{linhas}</ul>'
            f'<div class="rx-l-polo">▼ {html.escape(baixo)}</div>'
            f'<ul class="rx-l-extra">{"".join(extras)}</ul></div>')


def _extremos(unidades: pd.DataFrame, metrica: str) -> None:
    piores, melhores = nar.extremos_mapa(unidades, metrica, "rotulo")
    if not piores:
        return
    lista = lambda pares: "".join(f"<li><span>{html.escape(n)}</span><b>{html.escape(v)}</b></li>"  # noqa: E731
                                  for n, v in pares)
    st.html('<div class="rx-painel"><p class="rx-l-titulo">Pior situação</p>'
            f'<ul class="rx-l-rank">{lista(piores)}</ul>'
            '<p class="rx-l-titulo">Melhor situação</p>'
            f'<ul class="rx-l-rank">{lista(melhores)}</ul></div>')


def _mapa(ctx: c.Contexto) -> None:
    """Um único mapa de SC: o filtro troca o indicador (e a paleta); o círculo mostra o volume."""
    with st.container(border=True, key="rx-destaque"):
        escolha, nivel_col, bolha_col = st.columns([4, 4, 2], vertical_alignment="bottom")
        metrica = escolha.selectbox("O que mostrar no mapa", METRICAS_MAPA,
                                    format_func=lambda m: c.DEFINICOES[m].rotulo, key="mapa_metrica")
        nivel = nivel_col.segmented_control("Pintar por", [c.NIVEL_MESO, c.NIVEL_MICRO, c.NIVEL_MUNICIPIO],
                                            default=c.NIVEL_MUNICIPIO, key="mapa_nivel") or c.NIVEL_MUNICIPIO
        bolhas = bolha_col.toggle("Volume", value=True, key="mapa_bolhas",
                                  help="Círculo em cada município, do tamanho das suas movimentações.")
        st.caption(nar.LEITURA_MAPA.get(metrica, ""))
        dados_mapa = metricas_mapa(ctx.df, nivel)
        unidades = dados_mapa.drop_duplicates("rotulo")
        # O estado do gráfico já traz o clique desta execução: lê antes de desenhar,
        # para o contorno do território clicado sair junto.
        atualizar_selecao(st.session_state.get("mapa"), nivel, st.session_state)
        sel = st.session_state.get("mapa_sel")
        alvo = sel[1] if sel and sel[0] == nivel and sel[1] in set(unidades["rotulo"]) else None
        destaque = list(ctx.filtros.territorios if ctx.filtros.nivel_territorial == nivel else ())
        destaque += [alvo] if alvo and alvo not in destaque else []
        mapa, lado = st.columns([5, 2], gap="medium")
        with mapa:
            st.plotly_chart(
                fig.construir_mapa(dados_mapa, c.geojson_cache(), metrica, rotulo_territorio="rotulo",
                                   destaque=destaque, altura=640, legenda=False,
                                   bolhas=volume_por_municipio(ctx.df, nivel) if bolhas else None),
                width="stretch", on_select="rerun", selection_mode="points", key="mapa",
                config={"scrollZoom": False, "displayModeBar": False, "doubleClick": False})
        with lado:
            _cartao_selecao(ctx, unidades, metrica, nivel, alvo)
            st.divider()
            _legenda(dados_mapa, metrica, nivel, bolhas)
            _extremos(unidades, metrica)


# --- Conceitos-chave e guia de decisão --------------------------------------------


def _ver_no_mapa(metrica: str) -> None:
    st.session_state["mapa_metrica"] = metrica


def _sinais(ctx: c.Contexto) -> None:
    ref = c.total(ctx.ref) if ctx.tem_recorte else None
    lista = nar.sinais(c.total(ctx.df), ref)
    for col, (i, s) in zip(st.columns(len(lista)), enumerate(lista)):
        estado = "alerta" if s.alerta else "ok"
        with col.container(border=True, height="stretch", key=f"rx-sinal-{estado}-{i}"):
            selo = "Sinal de alerta" if s.alerta else "Dentro da referência"
            st.html(f'<div class="rx-sinal"><div class="rx-s-titulo">{html.escape(s.titulo)}</div>'
                    f'<div class="rx-s-oque">{html.escape(s.o_que_e)}</div>'
                    f'<div class="rx-s-valor">{html.escape(s.valor)}</div>'
                    f'<div class="rx-s-ref">{html.escape(s.referencia)}</div>'
                    f'<span class="rx-selo rx-selo-{estado}">{selo}</span>'
                    f'<div class="rx-s-leitura">{html.escape(s.leitura)}</div></div>')
            if s.metrica in METRICAS_MAPA:
                st.button("Ver no mapa", key=f"sinal_mapa_{i}", on_click=_ver_no_mapa, args=(s.metrica,),
                          icon=":material/map:", type="tertiary")


_CLASSE_QUADRANTE = {c.Q_APAGAO: "apagao", c.Q_PRESSAO: "pressao", c.Q_ESTAGNACAO: "estagnacao",
                     c.Q_SAUDAVEL: "saudavel"}


def _link(chave: str, rotulo: str, icone: str) -> None:
    pagina = st.session_state.get("_paginas", {}).get(chave)
    if pagina is not None:
        st.page_link(pagina, label=rotulo, icon=icone)


def _situacoes(ctx: c.Contexto) -> None:
    m = c.matriz_diagnostico(ctx.df, [c.COLUNA_REGIAO, c.COLUNA_SETOR])
    resumo = nar.resumo_quadrantes(m)
    tensao = resumo[c.Q_APAGAO][1] + resumo[c.Q_PRESSAO][1]
    if not m.empty:
        st.markdown(f"Cada grupo (um setor numa mesorregião) cai numa de quatro situações, conforme **cresce ou "
                    f"não** e **segura ou perde gente**. Hoje, **{c.fmt_pct(tensao, 0)} das movimentações** estão "
                    "nas duas situações de alerta (linha de cima).")
    # Mesma disposição da matriz: em cima, perde gente; à direita, cresce.
    for linha in ((c.Q_APAGAO, c.Q_PRESSAO), (c.Q_ESTAGNACAO, c.Q_SAUDAVEL)):
        for col, q in zip(st.columns(2), linha):
            como, fazer = nar.GUIA_QUADRANTES[q]
            n, frac = resumo[q]
            with col.container(border=True, height="stretch", key=f"rx-quad-{_CLASSE_QUADRANTE[q]}"):
                st.html(f'<span class="rx-semaforo rx-{_CLASSE_QUADRANTE[q]}">{html.escape(q)}</span>'
                        f'<div class="rx-q-como">{html.escape(como)}</div>'
                        f'<div class="rx-q-fazer"><b>O que fazer:</b> {html.escape(fazer)}</div>'
                        f'<div class="rx-q-n"><b>{n}</b> {"grupo" if n == 1 else "grupos"} · '
                        f'<b>{c.fmt_pct(frac, 0)}</b> das movimentações</div>')
    _link("diagnostico", "Ver cada grupo em Quem precisa de atenção", ":material/crisis_alert:")


PRIORIDADES_MAX = 3


def _prioridades(ctx: c.Contexto) -> None:
    # Do estado (só escopo e período), como os achados: aplicar uma não reescreve a lista.
    recs = c.gerar_recomendacoes(ctx.ref)
    if not recs:
        st.caption("Nenhuma ação disparou com dados suficientes nesta seleção.")
        return
    st.markdown(f"As {PRIORIDADES_MAX} primeiras de {len(recs)} ações, ordenadas pelo tamanho do problema "
                "(gravidade × número de pessoas afetadas).")
    for i, r in enumerate(recs[:PRIORIDADES_MAX]):
        filtros = {"f_nivel": c.NIVEL_MESO, "f_terr": [r.regiao], "f_macro": [r.macrofamilia]}
        ativo = achado_ativo(filtros, st.session_state)
        with st.container(border=True, key=f"rx-achado-p{i}" + ("-ativo" if ativo else "")):
            texto, botao = st.columns([5, 1], vertical_alignment="center")
            texto.markdown(f"**{i + 1}. {r.alavanca}** — {r.macrofamilia} em **{r.regiao}**  \n"
                           f"{POR_QUE_ALAVANCA.get(r.alavanca, '')} "
                           f":gray[Evidência: {r.evidencia}; {c.fmt_int(r.movimentacoes)} movimentações.]")
            if ativo:
                botao.button("Voltar ao estado", key=f"prio_{i}", on_click=aplicar_achado, args=({},),
                             icon=":material/undo:", width="stretch", type="primary")
            else:
                botao.button("Ver evidência", key=f"prio_{i}", on_click=aplicar_achado, args=(filtros,),
                             icon=":material/filter_alt:", width="stretch")
    _link("recomendacoes", f"Ver as {len(recs)} ações em O que fazer", ":material/lightbulb:")


def _achados(ctx: c.Contexto) -> None:
    # Achados do estado (só escopo e período): aplicar um deles não pode
    # reescrever a própria lista, senão os demais somem.
    achados = nar.principais_achados(ctx.ref)
    if not achados:
        st.caption("Sem dados suficientes para gerar achados nesta seleção.")
    for i, achado in enumerate(achados):
        ativo = achado_ativo(achado.filtros, st.session_state)
        with st.container(border=True, key=f"rx-achado-{i}" + ("-ativo" if ativo else "")):
            texto, botao = st.columns([5, 1])
            texto.markdown(f"**{i + 1}. {achado.titulo}** — {achado.texto}")
            if ativo:
                botao.button("Voltar ao estado", key=f"achado_{i}", on_click=aplicar_achado, args=({},),
                             icon=":material/undo:", width="stretch", type="primary")
            else:
                botao.button("Ver evidência", key=f"achado_{i}", on_click=aplicar_achado, args=(achado.filtros,),
                             icon=":material/filter_alt:", width="stretch")


def _secoes_e_meses(ctx: c.Contexto) -> None:
    st.dataframe(ranking_secoes(ctx.df), hide_index=True, width="stretch", column_config={
        "Saldo de vagas": st.column_config.NumberColumn(format="localized"),
        "Movimentações": st.column_config.NumberColumn(format="localized"),
        "Rotatividade descontada": st.column_config.ProgressColumn(
            "Troca de equipe no ano", format="percent", min_value=0.0, max_value=1.0,
            help="Rotatividade descontada (MTE): min(admissões, desligamentos descontados) ÷ estoque de "
                 "31/12/2025 (RAIS). Oficial: SC 33,6%, Brasil 34,2%."),
        "Saída voluntária": st.column_config.ProgressColumn(
            "Saem a pedido", format="percent", min_value=0.0, max_value=1.0,
            help="Desligamentos a pedido ÷ desligamentos. Vazio = menos de 100 movimentações."),
    })
    st.caption("Da seção que mais criou vagas para a que mais perdeu. Vazio = poucos dados.")
    mensal = c.agregar_metricas(ctx.df, [c.COLUNA_MES])
    st.plotly_chart(fig.construir_serie_mensal(mensal), width="stretch")
    st.caption(nar.legenda_serie(mensal))


def render(ctx: c.Contexto) -> None:
    st.title("Onde está o problema?")
    c.cabecalho(ctx)
    if ctx.df.empty:
        st.info("Nenhuma movimentação com estes filtros. Use **Limpar filtros** na barra lateral.")
        return

    manchete = nar.resposta_principal(ctx.df, ctx.filtros.escopo).partition("\n\n")[0]
    with st.container(border=True):
        st.markdown(f"#### {manchete}")
        st.html('<ol class="rx-passos"><li><b>1. Os sinais:</b> quais estão em alerta</li>'
                '<li><b>2. Onde acontece:</b> o mapa por território</li>'
                '<li><b>3. Como decidir:</b> a situação de cada grupo</li>'
                '<li><b>4. Por onde começar:</b> as ações prioritárias</li></ol>')

    st.subheader("1. Os quatro sinais do apagão de mão de obra")
    _sinais(ctx)

    st.subheader("2. Onde acontece")
    _mapa(ctx)

    st.subheader("3. Como decidir: em que situação cada grupo está")
    _situacoes(ctx)

    st.subheader("4. Por onde começar")
    _prioridades(ctx)

    st.subheader("Aprofundar")
    c.cartoes_kpi(ctx, [m for m in c.METRICAS_TEMAS if m not in c.KPIS_PADRAO])
    with st.expander("Principais achados", icon=":material/lightbulb:"):
        _achados(ctx)
    with st.expander("Seções e evolução mês a mês", icon=":material/bar_chart:"):
        _secoes_e_meses(ctx)

    reagregado = c.agregar_metricas(ctx.df, [c.COLUNA_REGIAO, c.COLUNA_SETOR, c.COLUNA_MACROFAMILIA_CBO,
                                             c.COLUNA_NIVEL_QUALIFICACAO])
    c.baixar_csv(reagregado[reagregado[c.M_MOV] > 0], "panorama_recorte.csv")
