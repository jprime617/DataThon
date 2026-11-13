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

# ---------------------------------------------------------------------------
# Alavancas do motor de recomendações
# ---------------------------------------------------------------------------

ALAVANCA_SALARIO = "Revisar faixas salariais de entrada"
ALAVANCA_FORMACAO = "Formação técnica e parcerias de qualificação"
ALAVANCA_MOBILIDADE = "Recrutamento inter-regional e mobilidade"
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
