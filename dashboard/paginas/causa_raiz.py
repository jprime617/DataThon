"""3. Causa raiz — "Por quê: salário, qualificação ou estrutura?"."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar
from src.mapeamentos import FAIXAS_ESCOLARIDADE

ORDEM_FAIXAS = [rotulo for _, rotulo in FAIXAS_ESCOLARIDADE]


def perfil_filtrado(ctx: c.Contexto) -> tuple[pd.DataFrame | None, str]:
    """Recorta o perfil (mesorregião × setor × macrofamília × nível × faixa).

    O perfil não tem município nem mês: uma seleção de micro/município usa as
    mesorregiões que a contêm, e o período é sempre o inteiro.
    """
    perfil = ctx.art.perfil
    if perfil is None:
        return None, ""
    f = ctx.filtros
    nota = "Medianas do período inteiro"
    regioes: list[str] = []
    if f.territorios:
        regioes = sorted(ctx.df[c.COLUNA_REGIAO].astype(str).unique())
        if f.nivel_territorial != c.NIVEL_MESO:
            nota += f", pela(s) mesorregião(ões) da seleção: {', '.join(regioes)}"
    sel = perfil
    sel = sel[c.mascara_escopo(sel, f.escopo)]
    sel = c.aplicar_filtros(sel, regiao=regioes, **{c.COLUNA_SETOR: f.setores,
                                                    c.COLUNA_MACROFAMILIA_CBO: f.macrofamilias,
                                                    c.COLUNA_NIVEL_QUALIFICACAO: f.niveis})
    return sel, nota + ". Ao juntar células, a mediana é a mediana das medianas ponderada pelo número de salários."


def legenda_compressao(medianas: pd.DataFrame, categoria: str) -> str:
    dados = medianas[(medianas["n_admissao"] >= c.MIN_SALARIOS) & (medianas["n_desligamento"] >= c.MIN_SALARIOS)].copy()
    if dados.empty:
        return ""
    dados["razao"] = dados["mediana_admissao"] / dados["mediana_desligamento"]
    pior = dados.loc[dados["razao"].idxmin()]
    return (f"Maior compressão em **{pior[categoria]}**: a mediana de quem entra é "
            f"{c.fmt_pct(pior['razao'], 0)} da de quem sai ({c.fmt_brl(pior['mediana_admissao'])} vs "
            f"{c.fmt_brl(pior['mediana_desligamento'])}).")


def selos_por_unidade(ctx: c.Contexto, unidades: pd.DataFrame) -> pd.DataFrame:
    """Mesorregião × setor com ao menos uma causa (Salarial, Qualificação, Retenção), da maior para a menor."""
    ref = c.total(ctx.ref)  # ANA-01: referência = estado inteiro, mesmo escopo e período
    por = [c.COLUNA_REGIAO, c.COLUNA_SETOR]
    frac = c.fracao_por_nivel(ctx.df, por, c.NIVEIS_QUALIFICADOS)
    cbos, gap_ref_cbo = c.referencia_cbo(ctx)
    unidades = c.anexar_razao_cbo(unidades, cbos, por)  # ANA-01 P1: dentro da mesma CBO
    linhas = []
    for _, u in unidades.iterrows():
        selos = c.causas(u, saida_ref=ref[c.M_SAIDA_VOL], gap_ref=ref[c.M_GAP_SAL],
                         fracao_tecnica=float(frac.get((u[c.COLUNA_REGIAO], u[c.COLUNA_SETOR]), 0.0)),
                         gap_ref_cbo=gap_ref_cbo)
        if selos:
            linhas.append({"Grupo": f"{u[c.COLUNA_SETOR]} – {u[c.COLUNA_REGIAO]}", "Causas": " · ".join(selos),
                           "Movimentações": int(u[c.M_MOV]),
                           "Salário de quem entra vs quem saiu": c.fmt_gap(u[c.M_GAP_SAL]),
                           "Mesma razão no estado": c.fmt_gap(ref[c.M_GAP_SAL]),
                           "Na mesma ocupação (CBO)": c.fmt_gap(u.get(c.M_GAP_SAL_CBO)),
                           "Na mesma ocupação, no estado": c.fmt_gap(gap_ref_cbo),
                           "Saem a pedido": c.fmt_pct(u[c.M_SAIDA_VOL])})
    if not linhas:
        return pd.DataFrame(columns=["Grupo", "Causas", "Movimentações"])
    return pd.DataFrame(linhas).sort_values("Movimentações", ascending=False)


def resumo_causas(selos: pd.DataFrame, total: int) -> str:
    """Quantos grupos têm cada causa, em linguagem leiga."""
    if selos.empty:
        return f"Nenhum dos {total} grupos analisados tem uma causa clara nos dados."
    textos = {c.CAUSA_SALARIAL: "o salário de entrada perde mais para o de quem saiu do que no estado",
              c.CAUSA_RETENCAO: "o problema é reter (o salário de entrada não é pior que o do estado)",
              c.CAUSA_QUALIFICACAO: "entra gente com menos estudo numa área técnica"}
    linhas = [f"- **{selos['Causas'].str.contains(causa).sum()}** grupos: {texto}"
              for causa, texto in textos.items() if selos["Causas"].str.contains(causa).any()]
    return (f"Dos {total} grupos (setor × mesorregião) analisados:\n\n" + "\n".join(linhas)
            + "\n\nUm grupo pode ter mais de uma causa.")


def _delta_pp(diferenca: float) -> str:
    """Delta em p.p. com o hífen ASCII: o `st.metric` só desenha a seta para baixo com "-"."""
    return f"{c.fmt_pp(diferenca * 100).replace('−', '-')} vs desligados"


def _escolaridade_contratacao(ctx: c.Contexto, perfil: pd.DataFrame | None, nota: str) -> None:
    """ANA-02: participação de admitidos × desligados por escolaridade e o prêmio do diploma."""
    st.subheader("Escolaridade: o mercado contrata mais instruídos e paga mais por isso?", anchor=False)
    if perfil is None or perfil.empty:
        st.info("Perfil de escolaridade indisponível para esta seleção.")
        return
    t = c.escolaridade_contratacao(perfil).iloc[0]
    estado_perfil = ctx.art.perfil[c.mascara_escopo(ctx.art.perfil, ctx.filtros.escopo)]
    premio_estado = c.escolaridade_contratacao(estado_perfil).iloc[0]["premio"]
    col1, col2, col3 = st.columns(3)
    col1.metric("Admitidos com médio completo ou mais", c.fmt_pct(t["medio_adm"]), border=True,
                delta=_delta_pp(t['medio_adm'] - t['medio_desl']),
                help="De cada 100 contratados, quantos têm ao menos o ensino médio completo. "
                     "A seta compara com quem saiu.")
    col2.metric("Admitidos com superior completo", c.fmt_pct(t["superior_adm"]), border=True,
                delta=_delta_pp(t['superior_adm'] - t['superior_desl']),
                help="De cada 100 contratados, quantos têm curso superior completo. A seta compara com quem saiu.")
    col3.metric("Prêmio do diploma superior", nar.fmt_premio(t["premio"]), border=True,
                delta=f"estado: {nar.fmt_premio(premio_estado)}", delta_color="off", delta_arrow="off",
                help="Quantas vezes o salário de entrada de quem tem superior completo vale o de quem tem médio "
                     "completo. Cálculo: mediana de admissão com superior completo ÷ com médio completo "
                     f"(≥ {c.MIN_SALARIOS} salários em cada faixa).")
    st.markdown(nar.resposta_escolaridade_contratacao(t))
    grupos = c.escolaridade_contratacao(perfil, [c.COLUNA_REGIAO, c.COLUNA_SETOR])
    destaque = nar.destaque_premio_baixo(
        grupos, premio_estado, lambda g: f"{g[c.COLUNA_SETOR]} – {g[c.COLUNA_REGIAO]}")
    if destaque:
        st.warning(destaque, icon=":material/school:")
    with st.expander("Aprofundar: prêmio do diploma por macrofamília e por grupo"):
        macros = c.escolaridade_contratacao(perfil, [c.COLUNA_MACROFAMILIA_CBO])
        macros = macros[macros[c.COLUNA_MACROFAMILIA_CBO] != c.NAO_CLASSIFICADO]
        st.plotly_chart(fig.construir_premio(macros, c.COLUNA_MACROFAMILIA_CBO, premio_estado), width="stretch")
        st.caption("Vermelho hachurado = prêmio pelo menos "
                   f"{c.fmt_pct(1 - c.FATOR_PREMIO_BAIXO, 0)} abaixo do prêmio do estado. Dentro de uma mesma "
                   "ocupação industrial, o diploma superior quase não muda o salário de entrada. " + nota)
        tabela = grupos.dropna(subset=["premio"]).sort_values("premio")
        st.dataframe(pd.DataFrame({
            "Grupo": tabela[c.COLUNA_SETOR] + " – " + tabela[c.COLUNA_REGIAO],
            "Admitidos com médio ou mais": [c.fmt_pct(v) for v in tabela["medio_adm"]],
            "Desligados com médio ou mais": [c.fmt_pct(v) for v in tabela["medio_desl"]],
            "Admitidos com superior": [c.fmt_pct(v) for v in tabela["superior_adm"]],
            "Desligados com superior": [c.fmt_pct(v) for v in tabela["superior_desl"]],
            "Prêmio do diploma": [nar.fmt_premio(v) for v in tabela["premio"]],
            "Prêmio baixo": ["sim" if c.premio_baixo(v, premio_estado) else "" for v in tabela["premio"]],
        }), hide_index=True, width="stretch")


def _benchmark_brasil(ctx: c.Contexto) -> None:
    """ANA-04: a saída voluntária de SC contra a do Brasil (mesmas regras, mesmo período), com IC por bootstrap."""
    brasil = c.brasil_cache()
    tab = c.benchmark_brasil(ctx.ref, brasil, ctx.filtros.meses)
    transf = ctx.ref[ctx.ref[c.COLUNA_SECAO_INDUSTRIAL].astype(str) == c.SECAO_TRANSFORMACAO]
    rot = c.total(transf)[c.M_ROT_DESC] if not transf.empty else float("nan")
    st.markdown(nar.texto_benchmark(tab, c.saida_voluntaria_economia(brasil, ctx.filtros.meses), rot))
    if tab.empty:
        return
    st.plotly_chart(fig.construir_benchmark(tab), width="stretch")
    st.caption(
        "Brasil: os mesmos arquivos do Novo CAGED (MOV + FOR − EXC, todas as UFs, inclusive SC), com as mesmas regras "
        "e o mesmo período. O intervalo de SC sai de reamostrar os municípios "
        f"{c.fmt_int(c.N_BOOTSTRAP)} vezes (bootstrap): "
        "se o Brasil cai dentro dele, a diferença não se distingue do acaso geográfico. Compara o estado inteiro, "
        "sem os filtros de território, setor, macrofamília e nível.")
    st.dataframe(pd.DataFrame({
        "Seção (CNAE)": tab["secao"], "Desligamentos em SC": tab["desligamentos"].astype("int64"),
        "SC: a pedido": [c.fmt_pct(v) for v in tab["sc"]],
        f"IC {c.fmt_num(c.CONFIANCA * 100, 0)}% de SC": [f"{c.fmt_pct(a)} a {c.fmt_pct(b)}"
                                                         for a, b in zip(tab["ic_inf"], tab["ic_sup"])],
        "Brasil: a pedido": [c.fmt_pct(v) for v in tab["brasil"]],
        "Diferença": [c.fmt_pp(v) for v in tab["diferenca_pp"]], "Leitura": tab["leitura"],
    }), hide_index=True, width="stretch",
        column_config={"Desligamentos em SC": st.column_config.NumberColumn(format="localized")})


def render(ctx: c.Contexto) -> None:
    st.title("Por quê: salário, qualificação ou estrutura?", anchor=False)
    c.cabecalho(ctx)
    if ctx.df.empty:
        st.info("Nenhuma movimentação com estes filtros.")
        return
    c.cartoes_kpi(ctx, [c.M_GAP_SAL, c.M_SAL_ADM, c.M_SAL_DESL, c.M_GAP_ESC, c.M_SAIDA_VOL])

    perfil, nota = perfil_filtrado(ctx)
    unidades = c.agregar_metricas(ctx.df, [c.COLUNA_REGIAO, c.COLUNA_SETOR])
    unidades = unidades[unidades[c.M_AMOSTRA_OK]]
    selos = selos_por_unidade(ctx, unidades)

    st.subheader("Salário: quem entra ganha menos do que quem sai?", anchor=False)
    grafico, resumo = st.columns([3, 2], gap="large")
    por_macro = None
    if perfil is None or perfil.empty:
        grafico.info("Perfil de causa raiz indisponível para esta seleção.")
    else:
        por_faixa = c.medianas_perfil(perfil, [c.COLUNA_FAIXA_ESCOLARIDADE])
        por_faixa = por_faixa.set_index(c.COLUNA_FAIXA_ESCOLARIDADE).reindex(
            [f for f in ORDEM_FAIXAS if f in set(por_faixa[c.COLUNA_FAIXA_ESCOLARIDADE])]).reset_index()
        grafico.plotly_chart(fig.construir_salario_por_categoria(
            por_faixa, c.COLUNA_FAIXA_ESCOLARIDADE, "Mediana salarial por escolaridade"), width="stretch")
        grafico.caption(legenda_compressao(por_faixa, c.COLUNA_FAIXA_ESCOLARIDADE) + " " + nota)
        por_macro = c.medianas_perfil(perfil, [c.COLUNA_MACROFAMILIA_CBO])
    with resumo, st.container(border=True):
        st.markdown("**O que explica a perda de gente**")
        st.markdown(resumo_causas(selos, len(unidades)))

    _escolaridade_contratacao(ctx, perfil, nota)

    # No máximo 2 gráficos à vista (M3.C4): o resto fica em "Aprofundar".
    if por_macro is not None:
        with st.expander("Aprofundar: salário por profissão (macrofamília da IA)"):
            st.plotly_chart(fig.construir_salario_por_categoria(
                por_macro, c.COLUNA_MACROFAMILIA_CBO, "Mediana salarial por macrofamília (IA)"), width="stretch")
            st.caption(legenda_compressao(por_macro, c.COLUNA_MACROFAMILIA_CBO))
            quebra = nar.quebra_por_nivel(perfil)
            if quebra:
                st.caption(quebra)
    with st.expander("Aprofundar: qualificação e retenção"):
        col1, col2 = st.columns(2)
        macros = c.agregar_metricas(ctx.df, [c.COLUNA_MACROFAMILIA_CBO])
        macros = macros[macros[c.COLUNA_MACROFAMILIA_CBO].astype(str) != c.NAO_CLASSIFICADO]
        col1.plotly_chart(fig.construir_gap_escolaridade(macros, c.COLUNA_MACROFAMILIA_CBO), width="stretch")
        nota_esc = nar.destaque_escolaridade(ctx.df, perfil)
        if nota_esc:
            col1.caption(nota_esc)
        rot = unidades[c.COLUNA_SETOR].astype(str) + " – " + unidades[c.COLUNA_REGIAO].astype(str)
        col2.plotly_chart(fig.construir_dispersao(unidades, rot, c.M_GAP_SAL, c.M_SAIDA_VOL,
                                                  "Salário explica a saída voluntária?"), width="stretch")
        validas = unidades.dropna(subset=[c.M_GAP_SAL, c.M_SAIDA_VOL])
        if len(validas) >= 3:
            r = validas[c.M_GAP_SAL].corr(validas[c.M_SAIDA_VOL])
            col2.caption(f"Correlação entre a diferença salarial (entrada vs saída) e a saída voluntária: "
                         f"{c.fmt_num(r, 2)} ({len(validas)} mesorregião × setor com amostra). "
                         "Correlação não é causalidade.")
        # R7.4: salário médio de admissão × escolaridade ordinal média, por macrofamília.
        por_macro = macros[macros[c.M_SALARIO_OK]]
        st.plotly_chart(fig.construir_dispersao(por_macro, por_macro[c.COLUNA_MACROFAMILIA_CBO].astype(str),
                                                c.M_ESC_ADM, c.M_SAL_ADM,
                                                "Quem entra com mais estudo ganha mais? (por macrofamília)"),
                        width="stretch")
        st.caption("Cada bolha é uma macrofamília (IA); o tamanho é o volume de movimentações. "
                   f"Só macrofamílias com ≥ {c.MIN_SALARIOS} salários de cada lado. "
                   + nar.quebra_por_nivel(perfil))

    with st.expander("Aprofundar: estrutural ou local? SC × Brasil por seção"):
        _benchmark_brasil(ctx)

    with st.expander("Aprofundar: riqueza do município (IDHM e PIB per capita)"):
        col1, col2 = st.columns([1, 3])
        eixo_x = col1.radio("Indicador do município", [c.COLUNA_IDHM_2010, c.COLUNA_PIB_PER_CAPITA_2023],
                            format_func={c.COLUNA_IDHM_2010: "IDHM 2010",
                                         c.COLUNA_PIB_PER_CAPITA_2023: "PIB per capita 2023"}.get)
        eixo_y = col1.radio("Sintoma", [c.M_SAIDA_VOL, c.M_GAP_SAL, c.M_SALDO_10K],
                            format_func=lambda m: c.DEFINICOES[m].rotulo)
        municipios = c.agregar_metricas(ctx.df, [c.COLUNA_NOME_MUNICIPIO])
        contexto = ctx.df[[c.COLUNA_NOME_MUNICIPIO, eixo_x]].drop_duplicates(c.COLUNA_NOME_MUNICIPIO)
        municipios = municipios.merge(contexto, on=c.COLUNA_NOME_MUNICIPIO, how="left")
        municipios = municipios[municipios[c.M_AMOSTRA_OK]]
        col2.plotly_chart(fig.construir_dispersao(municipios, municipios[c.COLUNA_NOME_MUNICIPIO], eixo_x, eixo_y,
                                                  "Municípios mais ricos têm menos tensão?"), width="stretch")
        validas = municipios.dropna(subset=[eixo_x, eixo_y])
        if len(validas) >= 3:
            col2.caption(f"Correlação: {c.fmt_num(validas[eixo_x].corr(validas[eixo_y]), 2)} entre "
                         f"{len(validas)} municípios com ≥ 100 movimentações. Correlação não é causalidade; "
                         "o IDHM é de 2010.")

    with st.expander(f"Ver os {len(selos)} grupos com causa identificada"):
        if selos.empty:
            st.caption("Nenhum grupo com causa identificada nesta seleção.")
        else:
            st.dataframe(selos, hide_index=True, width="stretch",
                         column_config={"Movimentações": st.column_config.NumberColumn(format="localized")})
            st.caption(nar.legenda_causas(c.total(ctx.ref), c.referencia_cbo(ctx)[1]))
