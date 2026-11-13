"""7. Metodologia e sistema — de onde vêm os números e quais são os limites."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import comum as c
from dashboard import figuras as fig
from dashboard import narrativa as nar

ARQUITETURA = """
digraph {
  rankdir=TB; bgcolor="transparent"; nodesep=0.4; ranksep=0.35;
  node [shape=box, style="rounded,filled", fillcolor="#E8F0F8", color="#0F4C81", fontname="Helvetica", fontsize=15, width=3];
  edge [color="#555555"];
  csv [label="Novo CAGED SC\\n(FTP do MTE, 24 meses:\\nMOV + FOR − EXC)"];
  rais [label="RAIS 2025\\n(estoque em 31/12)"];
  inpc [label="INPC (IBGE)\\ndeflator"];
  mun [label="Municípios SC\\n(IBGE)"];
  limpeza [label="Limpeza e\\ndecodificação"];
  juncao [label="Junção por\\nmunicípio"];
  ia [label="IA: CBO →\\nmacrofamília + nível\\n(classificação + auditoria)", fillcolor="#FFF1E0", color="#D55E00"];
  agreg [label="Agregação\\n(contagens aditivas,\\nperfil, metadados)"];
  blob [label="Azure Blob\\nStorage", fillcolor="#E0F0FF"];
  app [label="Azure App Service\\n(este painel)", fillcolor="#E0F0FF"];
  csv -> limpeza -> juncao -> ia -> agreg -> blob -> app;
  mun -> juncao;
  inpc -> limpeza;
  rais -> agreg;
  agreg -> app [style=dashed, label="cópia local\\n(fallback)", fontsize=11];
}
"""

LIMITES = """
- **24 meses de dados** (set/24–ago/26), reconstruídos do FTP do MTE como MOV + FOR − EXC e conferidos contra a base fornecida no bloco recente (diferença de +0,02% nas admissões e +0,005% nos desligamentos). O painel abre nos **últimos 12 meses** (o mesmo período da base fornecida); o bloco anterior só alimenta a aceleração.
- **O CAGED mede fluxos, não estoque, e não tem vagas abertas.** "Apagão" é inferido por sinais de tensão (rotatividade descontada, saída voluntária e desligamento precoce; a compressão salarial entra como causa), não observado.
- **Estoque de 31/12/2025 como aproximação do estoque médio.** A rotatividade descontada do MTE divide pelo estoque médio do período; usamos o estoque CLT de SC em 31/12/2025 (RAIS 2025, fonte pública do MTE), que cai no meio da janela set/25–ago/26. Resultado: SC 34,8% contra 33,6% na taxa oficial de out/25–set/26. Células sem movimentação no período ficam fora (≈ 1% do estoque). O antigo "giro" (mín ÷ máx) saiu porque era função exata do saldo relativo.
- **A RAIS só tem o vínculo CLT** (tipos 10–25 e 60–75): aprendizes, temporários e estatutários ficam fora; transferências (motivos 30–34) não contam como desligamento.
- **Salários são declarados pelo empregador** e estão **deflacionados pelo INPC a preços de ago/2026**; as medianas do perfil, ao juntar células, são aproximadas pela mediana ponderada.
- **IDHM é de 2010**; PIB per capita de 2023; população estimada 2026. Correlações territoriais não implicam causalidade.
- **A classificação por IA é uma interpretação**, mitigada por regras explícitas (A–D), conjunto fechado de famílias, justificativa obrigatória quando foge do prefixo da CBO e uma auditoria contra uma classificação anterior feita por outro modelo (ver Que profissional falta → auditoria).
- **Emprego formal CLT apenas**: informalidade, autônomos e PJ ficam fora.
"""

PROXIMOS = """
- **Feito:** a saída voluntária de SC × Brasil por seção, com intervalo de confiança por bootstrap de municípios (Por que acontece → "Estrutural ou local?").
- **Rotatividade do Brasil por seção:** pede o estoque nacional (RAIS de todas as regiões ou as tabelas oficiais do MTE); hoje só a da transformação é comparada, com a taxa oficial.
- Intervalos de confiança também para os grupos da matriz e para as causas; RAIS 2024 e estoque mensal rolado.
- Lista completa em `docs/ROADMAP.md`.
"""

# NAR-04: onde conferir cada um dos 5 critérios oficiais da banca (e, à parte, a engenharia).
CRITERIOS_BANCA = [
    ("1. Compreensão do problema e do contexto industrial",
     "Panorama → Resposta à pergunta central (apagão × expansão, com a definição do guia); escopo de abertura na "
     "indústria de transformação; construção separada como rotatividade estrutural; Metodologia → os quatro quadrantes."),
    ("2. Embasamento analítico e diagnóstico (premissas e limites)",
     "Quem precisa de atenção (matriz e causas); Por que acontece (salário com a correção do viés de tempo de casa, "
     "escolaridade, riqueza do município); Metodologia → índice, critérios de \"explica\", premissas e limites, "
     "funil de linhas e sensibilidade dos pesos."),
    ("3. Dashboard e storytelling",
     "Panorama (resposta em três linhas, mapa, indicadores com explicação em cada um) → Quem precisa de atenção → "
     "Por que acontece → O que fazer. Filtros na barra lateral; recorte vazio avisa, sem erro."),
    ("4. Recomendações e valor de negócio (ligação com as macrofamílias da IA)",
     "O que fazer → as 3 ações de maior impacto, as alavancas por regra explícita (formação com as CBOs a formar, "
     "atração de talentos com o par origem → destino), quem age, horizonte e meta; Que profissional falta → a "
     "classificação da IA e a auditoria."),
    ("5. Pitch de 3 minutos",
     "Roteiro: Panorama (resposta + mapa) → Quem precisa de atenção (matriz) → O que fazer (Top 3). O modo "
     "apresentação resume os cinco passos."),
]
ENGENHARIA = [
    ("Pipeline reprodutível", "notebooks/01_pipeline.ipynb do FTP do MTE ao Blob; README com o passo a passo."),
    ("Classificação por IA", "Prompts e respostas versionados em ia_cbo/; concordância e divergências na auditoria."),
    ("Implantação no Azure", "Este painel no Azure App Service, lendo do Azure Blob Storage (origem em Procedência)."),
    ("Testes automatizados", "pytest + Hypothesis cobrindo pipeline, métricas, regras e páginas (ver Qualidade do código)."),
]

GLOSSARIO = [
    ("Saldo", "Contratações menos desligamentos: positivo, o emprego cresceu; negativo, encolheu."),
    ("Saída voluntária", "Desligamentos a pedido do próprio trabalhador, em % de todos os desligamentos."),
    ("Rotatividade descontada", "Quanto da equipe foi trocada no período, descontando quem pediu para sair, se "
     "aposentou, morreu ou foi transferido (definição do Ministério do Trabalho)."),
    ("Desligamento precoce", "Quem saiu antes de completar 1 ano na empresa."),
    ("p.p. (ponto percentual)", "Diferença entre duas porcentagens: de 47% para 52% são 5 p.p."),
    ("z-score", "Quantos desvios-padrão um grupo está acima (positivo) ou abaixo (negativo) da média dos grupos. "
     "Serve para somar indicadores de escalas diferentes."),
    ("Dinamismo", "O quanto o emprego do grupo cresce, comparado aos outros grupos (eixo horizontal da matriz)."),
    ("Tensão", "O quanto o grupo perde gente, comparado aos outros: troca de equipe, pedidos de saída e saídas "
     "antes de 1 ano (eixo vertical da matriz)."),
    ("Macrofamília (IA)", "Grupo de ocupações (CBO) parecidas, definido pela classificação por IA."),
    ("Mesorregião", "Uma das 6 grandes regiões de SC definidas pelo IBGE."),
]


def _sensibilidade(ctx: c.Contexto) -> None:
    """Robustez do índice de tensão (veio de Quem precisa de atenção no M3.C8)."""
    if len(c.PESOS_TENSAO_PADRAO) < 2 or ctx.df.empty:
        return
    with st.expander("Sensibilidade: o top 10 de tensão muda com outros pesos?"):
        por = [c.COLUNA_REGIAO, c.COLUNA_SETOR]
        m = c.matriz_diagnostico(ctx.df, por)
        st.caption("Unidade: mesorregião × setor. Pesos iniciais iguais para os três sintomas. Mude-os e veja quantas "
                   "unidades permanecem no top 10 de tensão.")
        cols = st.columns(len(c.PESOS_TENSAO_PADRAO))
        pesos = {nome: col.slider(f"Peso: {c.ROTULO_COMPONENTE[nome]}", 0.0, 3.0, 1.0, 0.5)
                 for col, nome in zip(cols, c.PESOS_TENSAO_PADRAO)}
        if sum(pesos.values()) == 0:
            st.warning("Ao menos um peso precisa ser maior que zero.")
            return
        alt = c.matriz_diagnostico(ctx.df, por, pesos_tensao=pesos)
        rotulo = lambda d: list((d[c.COLUNA_SETOR].astype(str) + " – " + d[c.COLUNA_REGIAO].astype(str)).head(10))
        base10, alt10 = rotulo(m), rotulo(alt)
        st.markdown(f"**{len(set(base10) & set(alt10))} de {min(10, len(base10))}** unidades permanecem no top 10.")
        st.dataframe(pd.DataFrame({"Pesos iguais": pd.Series(base10), "Pesos escolhidos": pd.Series(alt10)},
                                  index=range(1, max(len(base10), len(alt10)) + 1)), width="stretch")


def tabela_setores() -> pd.DataFrame:
    """TAX-01: o mapeamento CNAE → setor usado no pipeline, direto de `src.mapeamentos`."""
    from src.mapeamentos import SETOR_POR_DIVISAO_TRANSFORMACAO

    por_setor: dict[str, list[int]] = {}
    for divisao, setor in sorted(SETOR_POR_DIVISAO_TRANSFORMACAO.items()):
        por_setor.setdefault(setor, []).append(divisao)
    return pd.DataFrame([{"Setor": s, "Divisões CNAE": ", ".join(f"{d:02d}" for d in ds)}
                         for s, ds in sorted(por_setor.items(), key=lambda x: x[1][0])])


def _comparacao_regra_salarial(ctx: c.Contexto) -> str:
    """Quantos grupos do recorte teriam o selo Salarial com o corte fixo antigo (< 0,95) e com a regra atual."""
    m = c.agregar_metricas(ctx.df, [c.COLUNA_REGIAO, c.COLUNA_SETOR])
    m = m[m[c.M_AMOSTRA_OK]].dropna(subset=[c.M_GAP_SAL])
    if m.empty:
        return ""
    gap_ref = c.total(ctx.ref)[c.M_GAP_SAL]
    antigo = int((m[c.M_GAP_SAL] < c.LIMIAR_COMPRESSAO).sum())
    relativo = int(sum(c.salario_pior_que_estado(g, gap_ref) for g in m[c.M_GAP_SAL]))
    texto = (f"Neste recorte, o corte fixo antigo (< {c.fmt_num(c.LIMIAR_COMPRESSAO, 2)}) daria o selo a {antigo} "
             f"dos {len(m)} grupos mesorregião × setor, sem separar nada; a regra relativa, a {relativo}.")
    cbos, gap_ref_cbo = c.referencia_cbo(ctx)
    if c.RAZAO_SALARIAL_MESMA_CBO and pd.notna(gap_ref_cbo):
        m = c.anexar_razao_cbo(m, cbos, [c.COLUNA_REGIAO, c.COLUNA_SETOR])
        final = int(sum(c.salario_pior_que_estado(*c.gap_causa(u, gap_ref, gap_ref_cbo)[:2]) for _, u in m.iterrows()))
        texto += (f" Comparando dentro da mesma ocupação, a do estado sobe de {c.fmt_pct(gap_ref, 0)} para "
                  f"{c.fmt_pct(gap_ref_cbo, 0)} e o selo fica com {final}.")
    return texto


def render(ctx: c.Contexto) -> None:
    st.title("Metodologia e sistema", anchor=False)
    c.cabecalho(ctx)
    meta = ctx.art.metadados or {}

    st.subheader("Arquitetura", anchor=False)
    _, centro, _ = st.columns([1, 2, 1])
    centro.graphviz_chart(ARQUITETURA, width="stretch")
    st.caption("O LLM roda só no pipeline local; o painel lê tabelas pré-agregadas de poucos MB, nunca microdados.")

    st.subheader("Procedência dos dados", anchor=False)
    linhas = meta.get("linhas", {})
    periodo = meta.get("periodo", {})
    st.markdown(
        f"- **Origem em uso:** {({'blob': 'Azure Blob Storage', 'local': 'cópia local do pacote'}).get(ctx.art.origem, '—')}\n"
        f"- **Gerado em:** {str(meta.get('gerado_em', '—'))[:16].replace('T', ' ')} · **commit do pipeline:** "
        f"`{meta.get('commit') or '—'}`\n"
        f"- **Período:** {c.rotulo_mes(periodo.get('inicio', ''))}–{c.rotulo_mes(periodo.get('fim', ''))} "
        f"({periodo.get('meses', '—')} meses)\n"
        + (f"- **Salário válido:** {meta['salario_valido']['regra']} (teto {c.fmt_brl(meta['salario_valido']['teto'])})"
           if meta.get("salario_valido", {}).get("teto") else "")
    )
    for aviso in ctx.art.avisos:
        st.caption(f":material/info: {aviso}")

    if linhas:
        etapas = nar.etapas_funil(linhas)
        st.plotly_chart(fig.construir_funil(etapas), width="stretch")
        st.caption(nar.texto_funil(etapas) + f" Agregado: {c.fmt_int(linhas.get('agregado', 0))} linhas; "
                   f"perfil: {c.fmt_int(linhas.get('perfil', 0))} linhas.")

    st.subheader("Definições", anchor=False)
    st.table(pd.DataFrame([{"Indicador": d.rotulo, "Fórmula": d.formula} for d in c.DEFINICOES.values()])
             .set_index("Indicador"))
    st.caption(f"Guarda de amostra: taxas exigem ≥ {c.MIN_MOVIMENTACOES} movimentações; gaps salariais, "
               f"≥ {c.MIN_SALARIOS} salários de admissão e de desligamento. Abaixo disso a célula fica em cinza "
               "e sai de rankings e da matriz.")

    st.subheader("Resposta à pergunta central: quando renda e escolaridade \"explicam\"", anchor=False)
    st.markdown(
        "Entre os grupos mesorregião × setor com amostra, medimos (1) a **correlação** entre o fator e a saída "
        "voluntária (negativa = quanto pior o fator, mais gente pede para sair) e (2) a **fração de grupos** com a "
        "causa correspondente (Salarial ou Qualificação).\n"
        f"- **Explica:** correlação ≤ {c.fmt_num(c.CORR_EXPLICA, 1)} **e** pelo menos "
        f"{c.fmt_pct(c.FRACAO_EXPLICA, 0)} dos grupos com a causa.\n"
        f"- **Explica em parte:** correlação ≤ {c.fmt_num(c.CORR_EXPLICA_PARTE, 1)} **ou** pelo menos "
        f"{c.fmt_pct(c.FRACAO_EXPLICA_PARTE, 0)} dos grupos com a causa (|r| ≥ 0,3 é a convenção usual de "
        "correlação moderada).\n"
        "- **Não explica:** abaixo disso. Uma macrofamília com gap de escolaridade fora da curva aparece como exceção.\n"
        "Correlação não é causalidade: o veredito diz se o fator acompanha a saída, não se a provoca.")

    st.subheader("Regras das recomendações", anchor=False)
    st.markdown("Cada recomendação de O que fazer sai de uma regra explícita, avaliada por mesorregião × "
                "macrofamília (IA), só em grupos com ≥ 100 movimentações. A referência é o estado inteiro no "
                "mesmo escopo e período.")
    st.table(pd.DataFrame([{"Alavanca": a, "Quando dispara": r} for a, r in c.REGRA_ALAVANCA.items()])
             .set_index("Alavanca"))

    st.subheader("Setores: divisão CNAE → setor", anchor=False)
    st.markdown("Na indústria de transformação (seção C), o setor agrupa divisões CNAE 2.0 (dois primeiros dígitos "
                "da subclasse). Nas demais seções, o setor é a própria seção.")
    st.table(tabela_setores().set_index("Setor"))

    st.subheader("Como a matriz é calculada: Dinamismo (cresce?) e Tensão (perde gente?)", anchor=False)
    st.markdown(
        "- **Dinamismo** = média dos z-scores da **variação do emprego** (saldo ÷ estoque de 31/12/2025) e da **aceleração** "
        "(saldo de set/25–ago/26 menos o de set/24–ago/25, ÷ estoque), entre as unidades com amostra. Blocos de 12 "
        "meses comparam o mesmo calendário, sem sazonalidade.\n"
        "- **Tensão** = média dos z-scores dos três **sintomas** de dificuldade de reter gente, com pesos iguais: "
        "**rotatividade descontada**, **saída voluntária** e **desligamento precoce** (< 12 meses de casa). "
        "O expander abaixo mostra se o top 10 muda com outros pesos.\n"
        "- **Causas não entram no índice.** A causa salarial, o gap de escolaridade e a retenção "
        "viram selos em Quem precisa de atenção e regras em O que fazer. Somá-las à tensão e depois usá-las para explicá-la "
        "seria contar a mesma coisa duas vezes.\n"
        f"- **Viés de tempo de casa (causa salarial).** Quem sai costuma ter mais tempo de casa do que quem entra, então "
        f"o salário de entrada ser menor é o esperado: no estado, quem entra ganha "
        f"{c.fmt_pct(c.total(ctx.ref)[c.M_GAP_SAL], 0)} do salário de quem sai. Por isso a causa **Salarial** é relativa: "
        f"só acende quando a razão entrada/saída do grupo fica **{c.fmt_num(c.MARGEM_SALARIAL_RELATIVA * 100, 0)} p.p. "
        "ou mais abaixo da razão do estado** (mesmo escopo e período). "
        "**Dentro da mesma ocupação:** a razão é calculada em cada CBO do grupo e depois ponderada pelas "
        f"movimentações (só CBOs com ≥ {c.MIN_SALARIOS} salários de cada lado). Assim a comparação é entre a mesma "
        "função, e não entra o efeito de contratar numa ocupação e perder gente noutra. Ela decide o selo quando as "
        f"CBOs com amostra cobrem ≥ {c.fmt_pct(c.MIN_COBERTURA_CBO, 0)} das movimentações do grupo; senão, vale a "
        "razão do grupo inteiro. "
        + _comparacao_regra_salarial(ctx) + "\n"
        "- **Saíram:** o giro (função exata do saldo relativo) e a aceleração entre semestres (media o calendário: "
        "dezembro concentra desligamentos); ela voltou na forma de blocos de 12 meses."
    )

    st.markdown(
        "**Demanda: a taxa de admissão.** O CAGED não tem vagas abertas; o proxy de demanda é a **taxa de admissão** "
        "(admissões ÷ estoque de 31/12/2025): quantas contratações o grupo fez para cada 100 empregos que tinha. "
        f"No recorte, a do estado é {c.fmt_pct(c.total(ctx.ref)[c.M_TAXA_ADM])}. **Demanda alta + retenção baixa** "
        "(contrata muito e perde a equipe) é o sinal de apagão do guia: o grupo precisa de gente e não consegue "
        "segurá-la. A taxa aparece no tooltip da matriz e na tabela de alertas de Quem precisa de atenção.")

    st.markdown("**Os quatro quadrantes** (Dinamismo ≥ 0 = cresce mais que a média dos grupos; Tensão ≥ 0 = perde "
                "a equipe mais que a média). Os eixos são relativos: um grupo pode estar do lado \"cresce\" com saldo "
                "pequeno ou até negativo, se a média for baixa; por isso as frases do painel citam o saldo. "
                "Pelo guia do desafio, apagão é demanda alta com escassez ou rotatividade forte: o grupo que "
                "cresce e não retém.")
    st.markdown("\n".join(f"- **{q}**: {d.eixos}." for q, d in c.QUADRANTES.items()))

    _sensibilidade(ctx)

    st.subheader("Onde conferir cada critério da banca", anchor=False)
    st.table(pd.DataFrame(CRITERIOS_BANCA, columns=["Critério", "Onde conferir"]).set_index("Critério"))
    st.markdown("**Engenharia**")
    st.table(pd.DataFrame(ENGENHARIA, columns=["Item", "Onde conferir"]).set_index("Item"))

    st.subheader("Premissas e limites", anchor=False)
    st.markdown(LIMITES)

    st.subheader("Qualidade do código", anchor=False)
    testes = meta.get("testes")
    repo, commit = c.REPO_URL, meta.get("commit")
    st.markdown(
        (f"- **{testes} testes automatizados** (pytest + Hypothesis) cobrindo pipeline, métricas, regras e páginas.\n"
         if testes else "")
        + f"- Código-fonte (público): [{repo}]({repo})"
        + (f" — commit do pipeline [`{commit}`]({repo}/commit/{commit})." if commit else ".")
    )

    st.subheader("Próximos passos", anchor=False)
    st.markdown(PROXIMOS)

    st.subheader("Glossário", anchor=False)
    st.markdown("\n".join(f"- **{termo}**: {texto}" for termo, texto in GLOSSARIO))
