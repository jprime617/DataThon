"""Regras do Lote D (P1 + ANA-04) do plano da banca."""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard import comum as c
from dashboard import narrativa as nar
from dashboard import regras as r
from tests.test_dashboard_metricas import _celula, _df

MESES_12 = [f"2025{m:02d}" for m in range(9, 13)] + [f"2026{m:02d}" for m in range(1, 9)]


# --- TAX-02: selo "Expansão concentrada" ---------------------------------------


@pytest.mark.parametrize("saldo, fm, nm, fu, nu, esperado", [
    (100, 0.40, 12, 0.10, 5, True),     # um mês com 40% do saldo positivo (borda conta)
    (100, 0.39, 12, 0.80, 5, True),     # um município com 80% (borda conta)
    (100, 0.39, 12, 0.79, 5, False),
    (100, 0.90, 3, 0.10, 5, False),     # poucos meses no filtro: 1 mês com 40% é o normal
    (100, 0.10, 12, 1.00, 1, False),    # um município só (ficha de município): regra não se aplica
    (-50, 0.90, 12, 1.00, 5, False),    # só vale para quem abriu vagas
    (0, 0.90, 12, 1.00, 5, False),
])
def test_regra_da_expansao_concentrada(saldo, fm, nm, fu, nu, esperado):
    assert r.expansao_concentrada(saldo, fm, nm, fu, nu) is esperado


def _grupo_por_mes(saldos: list[int], **extra) -> list[dict]:
    return [_celula(mes=m, admissoes=max(s, 0) + 10, desligamentos=max(-s, 0) + 10, **extra)
            for m, s in zip(MESES_12, saldos)]


def test_mes_com_40_por_cento_do_saldo_positivo_acende_o_selo():
    # 11 meses com +10 e um mês com +80: 80 / 190 = 42% do saldo positivo.
    df = _df(*_grupo_por_mes([10] * 11 + [80]))
    conc = c.concentracao_saldo(df, ["regiao", "setor"]).iloc[0]
    assert conc["fracao_mes"] == pytest.approx(80 / 190)
    assert conc["mes_pico"] == "202608"
    assert bool(conc["concentrada"])


def test_denominador_e_o_saldo_positivo_nao_o_liquido():
    """Município +44 e outros −38: com o saldo líquido (6) daria 733% e acenderia sempre."""
    df = _df(_celula(admissoes=44), _celula(municipio="420540", municipio_nome="Florianópolis", desligamentos=20),
             _celula(municipio="420820", municipio_nome="Itajaí", desligamentos=18),
             _celula(municipio="421130", municipio_nome="Navegantes", admissoes=40))
    conc = c.concentracao_saldo(df, ["regiao", "setor"]).iloc[0]
    assert conc["fracao_municipio"] == pytest.approx(44 / 84)
    assert not bool(conc["concentrada"])


def test_crescimento_espalhado_nao_acende():
    df = _df(*_grupo_por_mes([10] * 12))
    assert not bool(c.concentracao_saldo(df, ["regiao", "setor"]).iloc[0]["concentrada"])


def test_selo_vai_para_a_matriz_e_para_o_texto():
    df = _df(*_grupo_por_mes([10] * 11 + [300]),
             *_grupo_por_mes([10] * 12, setor="Têxtil"))
    por = ["regiao", "setor"]
    m = c.anexar_concentracao(c.agregar_metricas(df, por), df, por).set_index("setor")
    assert bool(m.loc["Metalurgia e produtos de metal", "concentrada"])
    assert not bool(m.loc["Têxtil", "concentrada"])
    texto = nar.texto_concentrada(m.loc["Metalurgia e produtos de metal"])
    assert texto.startswith(f"**{c.SELO_CONCENTRADA}**") and "ago/26" in texto
    assert nar.texto_concentrada(m.loc["Têxtil"]) == ""


def test_concentracao_de_recorte_vazio_nao_quebra():
    vazio = _df(_celula()).iloc[0:0]
    assert c.concentracao_saldo(vazio, ["regiao", "setor"]).empty
    m = c.anexar_concentracao(c.agregar_metricas(vazio, ["regiao", "setor"]), vazio, ["regiao", "setor"])
    assert "concentrada" in m.columns and m.empty


# --- ANA-02: escolaridade além da média ordinal ----------------------------------


def _perfil(**valores) -> dict:
    linha = {col: 0 for col in c.COLUNAS_ADITIVAS if not col.startswith(("soma_esc", "n_esc"))}
    linha.update({"regiao": "Oeste Catarinense", "setor": "Têxtil", "secao_industrial": c.SECAO_TRANSFORMACAO,
                  "escopo_industrial": True, "macrofamilia_cbo": "Têxtil, confecção, couro e calçados",
                  "nivel_qualificacao": "Qualificado", "faixa_escolaridade": "Médio completo",
                  "mediana_salario_admissao": 2000.0, "mediana_salario_desligamento": 2100.0})
    linha.update(valores)
    return linha


def test_participacao_por_escolaridade_e_premio_do_diploma():
    perfil = pd.DataFrame([
        _perfil(admissoes=60, desligamentos=50, n_salario_admissao=60, mediana_salario_admissao=2000.0),
        _perfil(faixa_escolaridade="Superior completo ou mais", admissoes=10, desligamentos=20,
                n_salario_admissao=40, mediana_salario_admissao=3000.0),
        _perfil(faixa_escolaridade="Fundamental completo", admissoes=30, desligamentos=30, n_salario_admissao=30),
    ])
    t = c.escolaridade_contratacao(perfil).iloc[0]
    assert t["medio_adm"] == pytest.approx(70 / 100)
    assert t["medio_desl"] == pytest.approx(70 / 100)
    assert t["superior_adm"] == pytest.approx(10 / 100)
    assert t["superior_desl"] == pytest.approx(20 / 100)
    assert t["premio"] == pytest.approx(1.5)
    assert "não está contratando gente mais instruída" not in nar.resposta_escolaridade_contratacao(t)
    assert "1,50×" in nar.resposta_escolaridade_contratacao(t)


def test_premio_exige_amostra_de_salarios_nas_duas_faixas():
    perfil = pd.DataFrame([
        _perfil(admissoes=60, n_salario_admissao=60),
        _perfil(faixa_escolaridade="Superior completo ou mais", admissoes=5, n_salario_admissao=c.MIN_SALARIOS - 1,
                mediana_salario_admissao=9000.0),
    ])
    assert pd.isna(c.escolaridade_contratacao(perfil).iloc[0]["premio"])


@pytest.mark.parametrize("premio, estado, esperado", [
    (1.18, 1.48, True),      # 1,48 × 0,8 = 1,184: abaixo
    (1.184, 1.48, True),     # na borda conta
    (1.20, 1.48, False),
    (float("nan"), 1.48, False),
])
def test_regra_do_premio_baixo_e_relativa_ao_estado(premio, estado, esperado):
    assert r.premio_baixo(premio, estado) is esperado


def test_destaque_cita_so_os_grupos_de_premio_baixo():
    tabela = pd.DataFrame({"setor": ["A", "B", "C"], "admissoes": [100, 50, 10], "premio": [1.03, 1.60, 1.10]})
    texto = nar.destaque_premio_baixo(tabela, 1.48, "setor")
    assert "**A** (1,03×)" in texto and "**C** (1,10×)" in texto and "**B**" not in texto
    assert nar.destaque_premio_baixo(tabela[tabela["setor"] == "B"], 1.48, "setor") is None


def test_escolaridade_contratacao_de_perfil_vazio():
    assert c.escolaridade_contratacao(None).empty
    assert "Sem dados" in nar.resposta_escolaridade_contratacao(None)


# --- TAX-05: decisões da IA além do prefixo da CBO -------------------------------------


def _mapa_ia() -> pd.DataFrame:
    return pd.DataFrame({
        "cbo2002ocupação": ["784205", "766315", "141510", "724315"],
        "descricao": ["Alimentador de Linha de Producao", "Operador de Acabamento (Industria Grafica)",
                      "Gerente de Restaurante", "Soldador"],
        "macrofamilia": ["Operação de linha e processo", "Operação de linha e processo",
                         "Serviços de apoio e outros", "Metalmecânica e eletroeletrônica"],
        "nivel_qualificacao": ["Básico", "Qualificado", "Superior", "Qualificado"],
        "justificativa": ["Ocupação elementar.", "766 é gráfica.", "Serviço de alimentação.", None],
    })


def _cbos_recorte() -> pd.DataFrame:
    return pd.DataFrame({"cbo": ["784205", "766315", "141510", "724315", "999999"],
                         "admissoes": [500, 30, 10, 50, 7], "desligamentos": [400, 20, 10, 50, 3]})


def test_decisoes_da_ia_separam_seguiu_contrariou_e_sem_prefixo():
    dec = c.decisoes_ia(_mapa_ia(), _cbos_recorte()).set_index("cbo")
    assert dec.loc["784205", "decisao"] == c.DECISAO_SEGUIU and bool(dec.loc["784205", "nivel_ajustado"])
    assert dec.loc["766315", "decisao"] == c.DECISAO_CONTRARIOU       # 76 → Têxtil pelo prefixo
    assert dec.loc["766315", "familia_prefixo"] == "Têxtil, confecção, couro e calçados"
    assert dec.loc["141510", "decisao"] == c.DECISAO_SEM_PREFIXO      # grande grupo 1 não tem prefixo
    assert dec.loc["724315", "decisao"] == c.DECISAO_SEGUIU and not bool(dec.loc["724315", "nivel_ajustado"])
    assert "999999" not in dec.index                                  # sem classificação: fora


def test_texto_das_decisoes_da_ia_e_calculado():
    dec = c.decisoes_ia(_mapa_ia(), _cbos_recorte())
    texto = nar.texto_decisoes_ia(dec)
    assert "**4 ocupações**" in texto
    assert "contrariou a família sugerida pelo prefixo da CBO em 1** (4,7% das movimentações)" in texto
    assert "sempre com justificativa" in texto
    assert "**Alimentador de Linha de Producao** (Qualificado → Básico, 900 movimentações)" in texto
    assert "Sem ocupações" in nar.texto_decisoes_ia(c.decisoes_ia(_mapa_ia(), _cbos_recorte().iloc[0:0]))


# --- NAR-05: mapa em mesorregião e "pior situação" com volume mínimo ---------------------


def _metricas_mapa() -> pd.DataFrame:
    df = _df(_celula(municipio_nome="Campo Alegre", municipio="420320", populacao_2026=12_000.0,
                     admissoes=60, desligamentos=340),
             _celula(municipio_nome="Joinville", admissoes=4_000, desligamentos=4_500))
    m = c.agregar_metricas(df, ["municipio_nome"])
    return m.assign(rotulo=m["municipio_nome"])


def test_pior_municipio_exige_volume_minimo():
    m = _metricas_mapa()  # Campo Alegre: 400 movimentações, saldo −280 em 12 mil hab.
    sem_nivel = nar.legenda_mapa(m, c.M_SALDO_10K, "rotulo")
    assert "**Campo Alegre**" in sem_nivel
    texto = nar.legenda_mapa(m, c.M_SALDO_10K, "rotulo", c.NIVEL_MUNICIPIO)
    assert "**Joinville**" in texto and f"≥ {c.fmt_int(c.MIN_MOV_PIOR_MUNICIPIO)} movimentações" in texto


def test_pior_situacao_diz_o_nivel_pintado():
    m = _metricas_mapa()
    assert "Pior situação entre as mesorregiões:" in nar.legenda_mapa(m, c.M_SALDO_10K, "rotulo", c.NIVEL_MESO)
    assert nar.minimo_pior_situacao(c.NIVEL_MESO) == c.MIN_MOVIMENTACOES
    assert nar.minimo_pior_situacao(c.NIVEL_MUNICIPIO) == c.MIN_MOV_PIOR_MUNICIPIO == 500


def test_mapa_abre_em_mesorregiao_sem_volume():
    import inspect

    from dashboard.paginas import panorama

    fonte = inspect.getsource(panorama._mapa)
    assert "default=c.NIVEL_MESO" in fonte
    assert 'toggle("Volume", value=False' in fonte
