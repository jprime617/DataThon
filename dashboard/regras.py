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

LIMIAR_COMPRESSAO = 0.95          # salário de entrada ÷ de saída abaixo disso = compressão
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
