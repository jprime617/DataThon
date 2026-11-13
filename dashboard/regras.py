"""Rótulos e limiares de negócio do painel, num lugar só.

Nomes de quadrantes, causas e alavancas, e os limiares que os disparam, moram
aqui (e só aqui). Assim, renomear um quadrante ou mudar um limiar muda a tela
inteira de forma consistente: legenda, cores, cartões, contagens, textos, a
Metodologia e o CSV exportado. `dashboard.comum` reexporta tudo, então
`c.Q_APAGAO` continua valendo.

Este módulo não importa nada do painel (evita import circular).
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Guardas de amostra
# ---------------------------------------------------------------------------

MIN_MOVIMENTACOES = 100   # taxas e matriz: grupos com menos que isso ficam fora
MIN_SALARIOS = 30         # gaps salariais: mínimo de salários de cada lado
# NAR-05: "Pior situação" do mapa por município só entre os que têm volume (um
# município de 120 movimentações não vira a manchete do estado).
MIN_MOV_PIOR_MUNICIPIO = 500

# ---------------------------------------------------------------------------
# Escopos (NAR-03)
# ---------------------------------------------------------------------------
# A banca e a Federação querem ver o parque de transformação (têxtil,
# metalmecânica, alimentos, eletroeletrônico): é o escopo de abertura. A
# construção (seção F) tem rotatividade estrutural de obra e fica identificada.

ESCOPO_TRANSFORMACAO = "Indústria de transformação (C)"
ESCOPO_INDUSTRIA = "Indústria (B–F)"
ESCOPO_ECONOMIA = "Toda a economia"
ESCOPOS = (ESCOPO_TRANSFORMACAO, ESCOPO_INDUSTRIA, ESCOPO_ECONOMIA)
ESCOPO_PADRAO = ESCOPO_TRANSFORMACAO
NOME_ESCOPO = {  # sujeito das frases do painel
    ESCOPO_TRANSFORMACAO: "A indústria de transformação catarinense",
    ESCOPO_INDUSTRIA: "A indústria catarinense",
    ESCOPO_ECONOMIA: "A economia catarinense",
}
AJUDA_ESCOPO = ("Transformação = seção CNAE C (alimentos, têxtil, metalmecânica, eletroeletrônico…). "
                "Indústria = seções B a F (soma extrativa, eletricidade e gás, água e resíduos e construção). "
                "A construção tem rotatividade estrutural (fim de obra) e aparece separada nos alertas.")
SECAO_TRANSFORMACAO = "Indústrias de Transformação"   # rótulo da seção C no dicionário do CAGED
SECAO_CONSTRUCAO = "Construção"                       # seção F
ROTULO_CONSTRUCAO = "Construção (rotatividade estrutural de obra)"
FRACAO_CONSTRUCAO = 0.5   # grupo com ≥ 50% das movimentações na seção F conta como construção


def inclui_construcao(escopo: str) -> bool:
    return escopo != ESCOPO_TRANSFORMACAO


# ---------------------------------------------------------------------------
# Quadrantes da matriz Dinamismo × Tensão (NAR-01)
# ---------------------------------------------------------------------------
# O guia do Datathon define:
#   - Apagão: alta demanda por trabalhadores com escassez de qualificados OU
#     forte rotatividade → o grupo que CRESCE e PERDE a equipe;
#   - Expansão acelerada: saldo forte de vagas → o grupo que CRESCE e SEGURA a equipe.
# Eixos: Dinamismo ≥ 0 = "cresce muito"; Tensão ≥ 0 = "perde a equipe".

Q_APAGAO = "Apagão: cresce, mas não retém"
Q_EXPANSAO = "Expansão acelerada"
Q_RETRACAO = "Retração com rotatividade"
Q_ESTAGNACAO = "Estagnação"


@dataclass(frozen=True)
class Quadrante:
    nome: str
    cresce: bool        # Dinamismo ≥ 0
    perde: bool         # Tensão ≥ 0
    eixos: str          # a posição na matriz, em linguagem leiga
    classe: str         # sufixo de classe CSS (cartões e semáforo)
    cor: str            # Okabe-Ito, segura para daltonismo
    nome_cor: str       # a cor por extenso, para a legenda em texto (nunca só cor)

    @property
    def alerta(self) -> bool:
        """Quadrantes que perdem a equipe entram em "Quem precisa de atenção"."""
        return self.perde


QUADRANTES: dict[str, Quadrante] = {
    q.nome: q for q in (
        Quadrante(Q_APAGAO, True, True, "cresce muito e perde a equipe", "apagao", "#D55E00", "vermelho"),
        Quadrante(Q_EXPANSAO, True, False, "cresce muito e segura a equipe", "expansao", "#0072B2", "azul"),
        Quadrante(Q_RETRACAO, False, True, "cresce pouco e perde a equipe", "retracao", "#E69F00", "laranja"),
        Quadrante(Q_ESTAGNACAO, False, False, "cresce pouco e segura a equipe", "estagnacao", "#8C8C8C", "cinza"),
    )
}
QUADRANTES_ALERTA = tuple(q for q, d in QUADRANTES.items() if d.alerta)
CORES_QUADRANTE = {q: d.cor for q, d in QUADRANTES.items()}


def quadrante(dinamismo: float, tensao: float) -> str:
    """Quadrante da matriz; zero conta como "alto" nos dois eixos."""
    cresce, perde = dinamismo >= 0, tensao >= 0
    return next(q for q, d in QUADRANTES.items() if d.cresce == cresce and d.perde == perde)


# ---------------------------------------------------------------------------
# Causas (selos) e seus limiares
# ---------------------------------------------------------------------------

CAUSA_SALARIAL = "Salarial"
CAUSA_QUALIFICACAO = "Qualificação"
CAUSA_RETENCAO = "Retenção"

LIMIAR_COMPRESSAO = 0.95          # salário de entrada ÷ de saída abaixo disso = compressão (leitura do gap)
# ANA-01: quem sai tem mais tempo de casa, então ganhar menos na entrada é o
# esperado (viés de tempo de casa). A causa "Salarial" passa a ser RELATIVA:
# a razão entrada/saída do grupo fica ≥ 3 p.p. abaixo da razão do estado inteiro
# (mesmo escopo e período). Antes, com o corte fixo em 0,95, 55 de 82 grupos
# recebiam o selo e ele não discriminava nada.
MARGEM_SALARIAL_RELATIVA = 0.03


def salario_pior_que_estado(gap: float, gap_estado: float) -> bool:
    """Causa "Salarial": razão entrada/saída ≥ 3 p.p. pior que a do estado."""
    # +1e-9: 0,94 − 0,03 vira 0,9099999… em ponto flutuante; a borda exata (3 p.p.) conta.
    return gap == gap and gap_estado == gap_estado and gap <= gap_estado - MARGEM_SALARIAL_RELATIVA + 1e-9


def salario_nao_explica(gap: float, gap_estado: float) -> bool:
    """O salário de entrada do grupo não é pior que o do estado (base da causa "Retenção")."""
    return gap == gap and gap_estado == gap_estado and gap >= gap_estado
LIMIAR_GAP_ESCOLARIDADE = -0.10   # gap de escolaridade (níveis) que acende "Qualificação"
NIVEIS_QUALIFICADOS = ("Técnico", "Superior")
MARGEM_SAIDA_VOLUNTARIA = 0.05    # saída voluntária ≥ referência + 5 p.p. = "alta"
# DATA-01: gap de escolaridade de uma macrofamília que merece nota explicativa
# (bem abaixo das demais, que ficam entre −0,12 e +0,07 no estado).
LIMIAR_DESTAQUE_GAP_ESC = -0.30

# ANA-02: escolaridade além da média ordinal. Faixas do perfil (src.mapeamentos.FAIXAS_ESCOLARIDADE).
FAIXA_MEDIO = "Médio completo"
FAIXA_SUPERIOR = "Superior completo ou mais"
FAIXAS_MEDIO_OU_MAIS = (FAIXA_MEDIO, "Superior incompleto", FAIXA_SUPERIOR)
# Prêmio do diploma = mediana de admissão com superior completo ÷ com médio completo.
# "Baixo" é relativo ao estado (mesmo escopo), como a causa Salarial: ≥ 20% abaixo do
# prêmio estadual. Com diploma que quase não paga, o grupo tende a não atrair qualificados.
FATOR_PREMIO_BAIXO = 0.80


def premio_baixo(premio: float, premio_estado: float) -> bool:
    """ANA-02: o prêmio salarial do superior no grupo está ≥ 20% abaixo do prêmio do estado?"""
    return premio == premio and premio_estado == premio_estado and premio <= premio_estado * FATOR_PREMIO_BAIXO + 1e-9


# ---------------------------------------------------------------------------
# Alavancas do motor de recomendações
# ---------------------------------------------------------------------------

ALAVANCA_SALARIO = "Revisar faixas salariais de entrada"
ALAVANCA_FORMACAO = "Formação profissional direcionada"
# REC-03: o CAGED não mede "sobra" de mão de obra; o nome diz só o que a regra sustenta.
ALAVANCA_MOBILIDADE = "Atração de talentos de outras regiões"
ALAVANCA_AUTOMACAO = "Automação e redesenho de postos"
ALAVANCA_RETENCAO = "Retenção não salarial"

# ---------------------------------------------------------------------------
# TAX-01: contexto externo de setores (só com fonte citada na tela)
# ---------------------------------------------------------------------------
# Fatos conferidos nas próprias matérias (13/11/2026). As fragatas da Marinha /
# Estaleiro Brasil Sul não aparecem nessas fontes e por isso não entram.

from src.mapeamentos import SETOR_POR_DIVISAO_TRANSFORMACAO as _SETOR_DIV  # noqa: E402

SETOR_NAVAL = _SETOR_DIV[30]
SETOR_VEICULOS = _SETOR_DIV[29]
CONTEXTO_SETOR = {
    SETOR_NAVAL: (
        "Contexto (fonte externa): em 26/06/2026 a Petrobras anunciou R$ 12 bilhões para 42 embarcações em "
        "Santa Catarina (Programa Mar Aberto), com 16 já em construção nos estaleiros Detroit Brasil (Itajaí) e "
        "Navship (Navegantes) — [Click Petróleo e Gás, 30/06/2026]"
        "(https://clickpetroleoegas.com.br/petrobras-despeja-r-12-bilhoes-no-litoral-de-santa-catarina-para-construir-"
        "42-embarcacoes-reacender-estaleiros-em-itajai-e-navegantes-gerar-mais-de-5-mil-empregos-e-transformar-a-indu-"
        "asaf04/). Antes, em 12/12/2024, contratos para 12 navios de apoio em Itajaí e Navegantes — "
        "[NSC Total](https://www.nsctotal.com.br/economia/contrato-bilionario-com-a-petrobras-traz-producao-de-navios-a-sc). "
        "Expansão puxada por encomendas tem data para acabar: não é tendência do setor."
    ),
}
# Concentração que merece ser dita no achado de expansão (município com ≥ 50% do saldo).
FRACAO_CONCENTRACAO_TEXTO = 0.5

# ---------------------------------------------------------------------------
# TAX-02: selo "Expansão concentrada" (projeto com data para acabar, não tendência)
# ---------------------------------------------------------------------------
# Num grupo (território × setor ou macrofamília) que abriu vagas, o selo acende
# quando um único mês responde por ≥ 40% do saldo positivo OU um único município
# por ≥ 80% dele. "Saldo positivo" = soma só dos meses (ou municípios) que
# abriram vagas: com o saldo líquido no denominador, um grupo de saldo 6 com um
# município +44 e outros −38 daria 733% e o selo acenderia em metade dos grupos.

SELO_CONCENTRADA = "Expansão concentrada"
LIMIAR_CONCENTRACAO_MES = 0.40
LIMIAR_CONCENTRACAO_MUNICIPIO = 0.80
# Com poucos meses no filtro, um mês ter 40% é o normal (3 meses = 33% cada).
MIN_MESES_CONCENTRACAO = 6


def expansao_concentrada(saldo: float, fracao_mes: float, n_meses: int,
                         fracao_municipio: float, n_municipios: int) -> bool:
    """TAX-02: o saldo positivo do grupo depende de um mês ou de um município?"""
    if not saldo == saldo or saldo <= 0:
        return False
    por_mes = n_meses >= MIN_MESES_CONCENTRACAO and fracao_mes == fracao_mes and fracao_mes >= LIMIAR_CONCENTRACAO_MES
    por_mun = (n_municipios >= 2 and fracao_municipio == fracao_municipio
               and fracao_municipio >= LIMIAR_CONCENTRACAO_MUNICIPIO)
    return bool(por_mes or por_mun)

# ---------------------------------------------------------------------------
# REC-01: regra da alavanca "Formação profissional direcionada"
# ---------------------------------------------------------------------------
# Grupo (mesorregião × macrofamília da IA) que CRESCE (Apagão ou Expansão
# acelerada), com nível-alvo Qualificado ou Técnico, e ao menos um sinal de
# falta de qualificação:
#   (a) gap de escolaridade < 0 (entra gente menos escolarizada do que sai);
#   (b) desligamento precoce acima do estado (o contratado não fica);
#   (c) a fração de Técnico + Superior entre os admitidos é menor que entre os
#       desligados (repõe com nível mais baixo).
# O "o que formar" são as CBOs de maior volume do grupo (código + descrição).

QUADRANTES_FORMACAO = (Q_APAGAO, Q_EXPANSAO)
NIVEIS_ALVO_FORMACAO = ("Qualificado", "Técnico")
# Materialidade: o plano pede "gap < 0", mas −0,03 nível é ruído (as
# macrofamílias variam entre −0,12 e +0,07 no estado). Abaixo de −0,05 conta.
LIMIAR_FORMACAO_GAP_ESC = -0.05
# Diferença mínima entre a fração de Técnico + Superior nos desligados e nos admitidos.
MARGEM_FORMACAO_TECNICO = 0.01
# Formação profissional industrial não se aplica a funções de escritório, comércio e apoio.
MACROFAMILIAS_FORA_FORMACAO = ("Administrativo e comercial", "Serviços de apoio e outros")
N_CBOS_FORMACAO = 5

# Regra de cada alavanca em linguagem leiga (Metodologia). Mantida ao lado dos
# limiares para que o texto e o código não se desencontrem.
REGRA_ALAVANCA = {
    ALAVANCA_FORMACAO: (
        "Grupo (mesorregião × macrofamília industrial) que cresce (Apagão ou Expansão acelerada), com nível-alvo "
        "Qualificado ou Técnico e ao menos um sinal de falta de qualificação: gap de escolaridade abaixo de "
        f"{str(LIMIAR_FORMACAO_GAP_ESC).replace('.', ',')} nível, desligamento precoce acima do estado, ou Técnico + "
        f"Superior pelo menos {int(MARGEM_FORMACAO_TECNICO * 100)} p.p. menos frequentes entre os admitidos do que entre "
        f"os desligados. Ficam fora {' e '.join(MACROFAMILIAS_FORA_FORMACAO)}. O \"o que formar\" são as "
        f"{N_CBOS_FORMACAO} CBOs com mais movimentações no grupo."),
    ALAVANCA_SALARIO: (
        "Razão salário de entrada ÷ salário de saída 3 p.p. ou mais abaixo da do estado e saída voluntária 5 p.p. "
        "ou mais acima da do estado."),
    ALAVANCA_RETENCAO: (
        "Saída voluntária 5 p.p. ou mais acima da do estado, com salário de entrada não pior que o do estado "
        "(o salário não explica a saída)."),
    ALAVANCA_MOBILIDADE: (
        "Destino: grupo em Apagão (cresce e não retém) com saldo positivo. Origem: a mesma macrofamília e o mesmo "
        "nível de qualificação em outra mesorregião, com saldo negativo e saída voluntária abaixo da do estado "
        "(fecha vagas por iniciativa do empregador, não por pedido de saída). Mostra o par origem → destino. O CAGED "
        "não mede vagas abertas nem desempregados: a origem indica onde há gente da mesma ocupação sendo "
        "dispensada."),
    ALAVANCA_AUTOMACAO: "Nível Básico com 50% ou mais das movimentações do grupo e saldo ≤ 0. Aparece como "
                        "observação, não como alavanca prioritária (ver abaixo).",
}

# REC-06: a regra de automação dispara 0–1 vez por escopo. Os grupos de nível Básico
# (Operação de linha, apoio) estão crescendo, em Apagão: a condição "saldo ≤ 0" é a
# que trava, e baixar o limiar de 50% não muda nada (com 30%, 3 casos). Automação
# também depende de investimento e produtividade, que o CAGED não mede. Por isso ela
# vira **observação**: fica fora do Top 3 e dos cartões de prioridade.
ALAVANCAS_OBSERVACAO = (ALAVANCA_AUTOMACAO,)
MOTIVO_OBSERVACAO = (
    "A regra de automação (nível Básico ≥ 50% e saldo ≤ 0) quase nunca dispara: os grupos de nível Básico estão "
    "crescendo. E automatizar depende de investimento e produtividade, que o CAGED não mede. Por isso é uma "
    "observação para a empresa avaliar, não uma prioridade.")


def eh_observacao(alavanca: str) -> bool:
    """REC-06: a alavanca aparece como observação, fora do Top 3 e das prioridades?"""
    return alavanca in ALAVANCAS_OBSERVACAO

# ---------------------------------------------------------------------------
# REC-02: quem age, horizonte e KPI de acompanhamento de cada alavanca
# ---------------------------------------------------------------------------

QUEM_AGE = {
    ALAVANCA_SALARIO: "Empresa",
    ALAVANCA_RETENCAO: "Empresa",
    ALAVANCA_FORMACAO: "Federação–SENAI",
    ALAVANCA_MOBILIDADE: "Empresa + Poder público",
    ALAVANCA_AUTOMACAO: "Empresa",
}
HORIZONTE = {
    ALAVANCA_SALARIO: "0–3 meses",
    ALAVANCA_RETENCAO: "0–3 meses",
    ALAVANCA_FORMACAO: "3–12 meses",
    ALAVANCA_MOBILIDADE: "3–12 meses",
    ALAVANCA_AUTOMACAO: "12+ meses",
}
# KPI candidatos de cada alavanca: (chave da métrica do painel, "menor é melhor").
# A meta usa o candidato em que o grupo está mais longe do estado, para pior
# (o sinal que disparou a recomendação); se nenhum está pior, "manter" o primeiro.
KPI_ALAVANCA = {
    ALAVANCA_SALARIO: (("gap_salarial", False),),
    ALAVANCA_RETENCAO: (("saida_voluntaria", True),),
    ALAVANCA_FORMACAO: (("gap_escolaridade", False), ("precoce", True)),
    ALAVANCA_MOBILIDADE: (("saida_voluntaria", True), ("rotatividade_desc", True), ("precoce", True)),
    ALAVANCA_AUTOMACAO: (("rotatividade_desc", True), ("saida_voluntaria", True)),
}
KPI_RESERVA = (("saida_voluntaria", True),)   # quando nenhum candidato tem dado no grupo
# Meta = andar esta fração da distância entre o grupo e o estado, no prazo abaixo.
FRACAO_META_DISTANCIA = 0.5
PRAZO_META_MESES = 12

# REC-04: ação padrão de cada alavanca ({macro}, {regiao}); formação e atração
# de talentos montam a própria ação (CBOs e par origem → destino).
ACAO_ALAVANCA = {
    ALAVANCA_SALARIO: "Revisar a faixa salarial de entrada de {macro} em {regiao}",
    ALAVANCA_RETENCAO: "Programa de retenção não salarial para {macro} em {regiao}",
    ALAVANCA_AUTOMACAO: "Avaliar automação e redesenho dos postos básicos de {macro} em {regiao}",
    ALAVANCA_FORMACAO: "Turmas de qualificação/aprendizagem industrial para {macro} em {regiao}",
    ALAVANCA_MOBILIDADE: "Atrair profissionais de {macro} para {regiao}",
}
TOP_EXECUTIVO = 3

# REC-05: simulador de custo da saída voluntária. Não há fonte no repositório
# para o custo de repor um trabalhador: é premissa do time, e a tela diz isso.
CUSTO_REPOSICAO_MIN, CUSTO_REPOSICAO_MAX, CUSTO_REPOSICAO_PADRAO = 1, 12, 3   # em salários
FONTE_CUSTO_REPOSICAO = "premissa do time, ajuste conforme a realidade da empresa"

# ---------------------------------------------------------------------------
# NAR-02: "renda / escolaridade explicam?" — limiares da resposta à pergunta central
# ---------------------------------------------------------------------------
# Medidos entre os grupos mesorregião × setor com amostra:
#   r = correlação entre o fator (razão salarial ou gap de escolaridade) e a
#       saída voluntária (negativa = quanto pior o fator, mais gente sai);
#   fração = grupos com a causa correspondente (Salarial ou Qualificação).
# "explica" exige as duas coisas fortes; "explica em parte", uma moderada
# (|r| ≥ 0,3 é a convenção usual de correlação moderada).
CORR_EXPLICA = -0.5
FRACAO_EXPLICA = 0.25
CORR_EXPLICA_PARTE = -0.3
FRACAO_EXPLICA_PARTE = 0.10
VEREDITO_EXPLICA, VEREDITO_PARTE, VEREDITO_NAO = "explica", "explica em parte", "não explica"


def veredito(r: float, fracao: float) -> str:
    """"explica" / "explica em parte" / "não explica", pelos limiares acima."""
    r_ok = r == r
    if r_ok and r <= CORR_EXPLICA and fracao >= FRACAO_EXPLICA:
        return VEREDITO_EXPLICA
    if (r_ok and r <= CORR_EXPLICA_PARTE) or fracao >= FRACAO_EXPLICA_PARTE:
        return VEREDITO_PARTE
    return VEREDITO_NAO
