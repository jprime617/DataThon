"""Regras determinísticas da classificação de CBO: nível, sugestão e liderança."""

from src.cbo_ia import _validar, familia_sugerida, lideranca, nivel_cbo


def test_nivel_cbo_pelo_primeiro_digito():
    assert nivel_cbo("142105") == "Superior"
    assert nivel_cbo("223505") == "Superior"
    assert nivel_cbo("391205") == "Técnico"
    assert nivel_cbo("784205") == "Qualificado"
    assert nivel_cbo("10105") == "Qualificado"  # grande grupo 0 sem zero à esquerda


def test_prefixo_mais_longo_vence():
    assert familia_sugerida("784205") == "Operação de linha e processo"
    assert familia_sugerida("782510") == "Logística e transporte"
    assert familia_sugerida("414105") == "Logística e transporte"
    assert familia_sugerida("411005") == "Administrativo e comercial"
    assert familia_sugerida("142105") is None  # dirigente: a IA decide


def test_flag_de_lideranca():
    assert lideranca("142105", "Gerente Administrativo")
    assert lideranca("410105", "Supervisor Administrativo")
    assert lideranca("710205", "Mestre (Construcao Civil)")
    assert not lideranca("784205", "Alimentador de Linha de Producao")


def test_divergencia_sem_justificativa_volta_para_a_regra():
    sem = _validar("784205", {"macrofamilia": "Logística e transporte", "nivel": "Básico"})
    assert sem["macrofamilia"] == "Operação de linha e processo"
    assert sem["nivel"] == "Qualificado"
    com = _validar("784205", {"macrofamilia": "Operação de linha e processo",
                              "nivel": "Básico", "justificativa": "elementar"})
    assert com["nivel"] == "Básico"
