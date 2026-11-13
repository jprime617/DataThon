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


# --- ANA-03: taxa de admissão (proxy de demanda) -------------------------------------


def test_taxa_de_admissao_e_admissoes_sobre_estoque():
    secao = {"secao_industrial": c.SECAO_TRANSFORMACAO}
    df = _df(_celula(admissoes=150, desligamentos=50, estoque_31dez=300, **secao),
             _celula(admissoes=50, desligamentos=50, setor="Têxtil", estoque_31dez=100, **secao))
    t = c.total(df)
    assert t[c.M_TAXA_ADM] == pytest.approx(200 / 400)
    assert c.fmt_metrica(c.M_TAXA_ADM, t[c.M_TAXA_ADM]) == "50,0%"
    assert pd.isna(c.total(_df(_celula(admissoes=10)))[c.M_TAXA_ADM])  # sem estoque, sem taxa


def test_taxa_de_admissao_vai_para_a_tabela_de_alertas():
    from dashboard.paginas import diagnostico

    df = _df(*[_celula(regiao=rg, admissoes=a, desligamentos=d, desligamentos_a_pedido=p, estoque_31dez=e,
                       municipio=mu, secao_industrial=c.SECAO_TRANSFORMACAO)
               for rg, a, d, p, e, mu in (("R1", 300, 200, 150, 500, "1"), ("R2", 100, 300, 30, 800, "2"),
                                          ("R3", 200, 200, 100, 600, "3"))])
    por = ["regiao", "setor"]
    m = c.matriz_diagnostico(df, por)
    tabela = diagnostico.tabela_alertas(m, "setor", c.total(df), pd.Series(dtype=float))
    assert {"Taxa de admissão", "Taxa de admissão no estado"} <= set(tabela.columns)
    assert tabela["Taxa de admissão no estado"].iloc[0] == "31,6%"   # 600 ÷ 1.900
    assert c.M_TAXA_ADM in c.DEFINICOES and c.M_TAXA_ADM in c.EXPLICACAO


# --- REC-05: simulador de custo ---------------------------------------------------------


def test_custo_de_reposicao_mostra_intervalo_premissa_e_limitacao():
    t = pd.Series({c.COLUNA_DESLIGAMENTOS_A_PEDIDO: 100_000, c.M_SAL_DESL: 2_500.0})
    assert c.custo_reposicao(t, 3) == pytest.approx(750_000_000)
    texto = nar.texto_custo_reposicao(t, 3)
    assert "R$ 750,0 mi" in texto
    assert "de R$ 250,0 mi a R$ 3,0 bi" in texto                    # 1 a 12 salários, formatador único
    assert c.FONTE_CUSTO_REPOSICAO in texto
    assert "todo desligamento a pedido é reposto" in texto
    assert "1 salário por" in nar.texto_custo_reposicao(t, 1)


# --- REC-06: automação como observação ---------------------------------------------------


def test_automacao_e_observacao_e_fica_fora_do_top3():
    from tests.test_dashboard_metricas import _rec

    assert r.eh_observacao(c.ALAVANCA_AUTOMACAO)
    assert not any(r.eh_observacao(a) for a in (c.ALAVANCA_SALARIO, c.ALAVANCA_FORMACAO, c.ALAVANCA_RETENCAO,
                                                 c.ALAVANCA_MOBILIDADE))
    recs = [_rec(c.ALAVANCA_AUTOMACAO, "Norte", "Apoio", 99, 9_999),     # a de maior volume
            _rec(c.ALAVANCA_RETENCAO, "Oeste", "Alimentos", 5, 400)]
    assert [x.alavanca for x in c.top_executivo(recs)] == [c.ALAVANCA_RETENCAO]
    assert "observação" in c.REGRA_ALAVANCA[c.ALAVANCA_AUTOMACAO]


# --- BUG-06: títulos sem link-âncora -------------------------------------------------------


def test_titulos_sem_link_ancora():
    import ast
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent / "dashboard"
    for arquivo in raiz.rglob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                    and no.func.attr in ("title", "header", "subheader") and no.args):
                ancora = next((k for k in no.keywords if k.arg == "anchor"), None)
                assert ancora is not None and getattr(ancora.value, "value", None) is False, \
                    f"{arquivo.name}:{no.lineno} sem anchor=False"
    assert 'stHeaderActionElements"] a[href^="#"] {display: none;}' in c._CSS


# --- TAX-06: script reproduzível de classificação pela API ------------------------------


def test_script_de_classificacao_tem_help():
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    saida = subprocess.run([sys.executable, str(raiz / "ia_cbo" / "classificar.py"), "--help"],
                           capture_output=True, text=True, timeout=120)
    assert saida.returncode == 0
    assert "LLM_API_KEY" in saida.stdout and "--provedor" in saida.stdout and "--saida" in saida.stdout


def test_script_grava_respostas_no_formato_do_chat(tmp_path):
    import json

    from ia_cbo.classificar import classificar_lotes, codigos_do_prompt
    from src.cbo_ia import _extrair_mapeamento

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "lote_01.txt").write_text("Classifique:\n- 784205 | Alimentador de Linha\n- 10105 | Oficial\n",
                                         encoding="utf-8")
    assert codigos_do_prompt((prompts / "lote_01.txt").read_text()) == {"784205", "010105"}

    class Falso:
        chamadas = 0

        def classificar(self, prompt, *, timeout):
            self.chamadas += 1
            if self.chamadas == 1:
                return "desculpe, sem JSON"          # 1ª tentativa vazia: tenta de novo
            return '```json\n{"784205": {"macrofamilia": "Operação de linha e processo", "nivel": "Básico", ' \
                   '"justificativa": "Elementar."}}\n```'

    falso = Falso()
    gravados = classificar_lotes(sorted(prompts.glob("lote_*.txt")), tmp_path / "saida", falso, espera=0,
                                 log=lambda *_: None)
    assert gravados == {"lote_01": 1} and falso.chamadas == 2
    arquivo = tmp_path / "saida" / "lote_01.json"
    assert _extrair_mapeamento(arquivo.read_text(encoding="utf-8"))["784205"]["nivel"] == "Básico"
    assert json.loads(arquivo.read_text(encoding="utf-8"))["784205"]["macrofamilia"] == "Operação de linha e processo"
    # Sem --sobrescrever, um lote já gravado não é refeito.
    assert classificar_lotes(sorted(prompts.glob("lote_*.txt")), tmp_path / "saida", falso, espera=0,
                             log=lambda *_: None) == {}


def test_script_exige_a_chave_antes_de_qualquer_chamada():
    from ia_cbo.classificar import criar_cliente
    from src.erros import ErroDeValidacao

    with pytest.raises(ErroDeValidacao):
        criar_cliente("anthropic", None, env={})


# --- ANA-01 (P1): razão salarial dentro da mesma CBO -----------------------------------


def _cbo(cbo, adm, desl, sal_adm, sal_desl, regiao="Norte Catarinense", setor="Metalurgia e produtos de metal"):
    return {"regiao": regiao, "setor": setor, "macrofamilia_cbo": "Metalmecânica e eletroeletrônica", "cbo": cbo,
            "admissoes": adm, "desligamentos": desl,
            "soma_salario_admissao": sal_adm * adm, "n_salario_admissao": adm,
            "soma_salario_desligamento": sal_desl * desl, "n_salario_desligamento": desl}


def _composicao() -> pd.DataFrame:
    """Cada ocupação paga igual na entrada e na saída; o grupo contrata a barata e perde a cara."""
    return pd.DataFrame([_cbo("784205", 900, 100, 2000, 2000), _cbo("214905", 100, 900, 8000, 8000)])


def test_razao_dentro_da_mesma_cbo_tira_o_efeito_de_composicao():
    cbos = _composicao()
    bruta = (cbos["soma_salario_admissao"].sum() / 1000) / (cbos["soma_salario_desligamento"].sum() / 1000)
    assert bruta == pytest.approx(2600 / 7400)                     # 35%: parece compressão salarial
    r = c.razao_mesma_cbo(cbos, ["regiao", "setor"]).iloc[0]
    assert r[c.M_GAP_SAL_CBO] == pytest.approx(1.0)                # na mesma função, ninguém ganha menos
    assert r[c.M_COBERTURA_CBO] == pytest.approx(1.0)


def test_media_ponderada_pelas_movimentacoes_e_so_cbos_com_amostra():
    cbos = pd.DataFrame([_cbo("A", 300, 100, 1800, 2000),          # razão 0,90, 400 movimentações
                         _cbo("B", 50, 50, 2000, 2000),            # razão 1,00, 100 movimentações
                         _cbo("C", 10, 90, 500, 5000)])            # 10 salários de admissão: fora
    r = c.razao_mesma_cbo(cbos, ["regiao", "setor"]).iloc[0]
    assert r[c.M_GAP_SAL_CBO] == pytest.approx((0.9 * 400 + 1.0 * 100) / 500)
    assert r[c.M_COBERTURA_CBO] == pytest.approx(500 / 600)
    assert c.razao_estado_mesma_cbo(cbos) == pytest.approx(0.92)
    assert pd.isna(c.razao_estado_mesma_cbo(None))


def test_causa_salarial_usa_a_mesma_cbo_quando_ha_cobertura(monkeypatch):
    linha = pd.Series({c.M_GAP_SAL: 0.80, c.M_GAP_SAL_CBO: 0.99, c.M_COBERTURA_CBO: 0.9, c.M_SAIDA_VOL: 0.40})
    assert c.CAUSA_SALARIAL in c.causas(linha, saida_ref=0.47, gap_ref=0.93)                    # sem ref por CBO: bruta
    assert c.CAUSA_SALARIAL not in c.causas(linha, saida_ref=0.47, gap_ref=0.93, gap_ref_cbo=0.96)
    pouca = linha.copy()
    pouca[c.M_COBERTURA_CBO] = c.MIN_COBERTURA_CBO - 0.01                                     # pouca cobertura: bruta
    assert c.CAUSA_SALARIAL in c.causas(pouca, saida_ref=0.47, gap_ref=0.93, gap_ref_cbo=0.96)
    assert c.gap_causa(linha, 0.93, 0.96) == (0.99, 0.96, True)
    monkeypatch.setattr(c, "RAZAO_SALARIAL_MESMA_CBO", False)                                 # a chave volta à bruta
    assert c.gap_causa(linha, 0.93, 0.96) == (0.80, 0.93, False)


def test_frase_do_cartao_diz_que_compara_a_mesma_ocupacao():
    from dashboard.paginas.diagnostico import frase_porque

    u = pd.Series({c.M_GAP_SAL: 0.85, c.M_GAP_SAL_CBO: 0.90, c.M_COBERTURA_CBO: 0.8, c.M_SAIDA_VOL: 0.6})
    frase = frase_porque(u, [c.CAUSA_SALARIAL], 0.47, 0.93, 0.96)
    assert frase.startswith("Na mesma ocupação, quem entra ganha 90%") and "(no estado, 96%)" in frase
    assert "na mesma ocupação" in nar.legenda_causas(pd.Series({c.M_GAP_SAL: 0.93}), 0.96)


# --- TAX-04 (P1): regra explícita de desempate ----------------------------------------------

OPERACAO, TEXTIL, APOIO = "Operação de linha e processo", "Têxtil, confecção, couro e calçados", "Serviços de apoio e outros"


@pytest.mark.parametrize("codigo, r1, r2, just, esperado", [
    ("784205", OPERACAO, OPERACAO, "", (OPERACAO, "IA (1ª rodada; as rodadas concordam)")),
    ("784205", OPERACAO, APOIO, "", (OPERACAO, "desempate: família do prefixo")),       # 1ª = prefixo
    ("766315", TEXTIL, OPERACAO, "", (TEXTIL, "desempate: família do prefixo")),         # 2ª desviou do prefixo 76
    ("766315", OPERACAO, TEXTIL, "", (TEXTIL, "desempate: família do prefixo")),         # 1ª desviou sem justificar
    ("766315", OPERACAO, TEXTIL, "766 é gráfica.", (OPERACAO, "desempate: 1ª rodada, desvio justificado")),
    ("141510", APOIO, "Alimentos e bebidas", "", (APOIO, "desempate: prefixo não resolve, 1ª rodada até revisão manual")),
    ("784205", OPERACAO, None, "", (OPERACAO, "IA (1ª rodada; sem 2ª rodada)")),
])
def test_regra_de_desempate(codigo, r1, r2, just, esperado):
    from src.cbo_ia import desempatar

    assert desempatar(codigo, r1, r2, just) == esperado


def _csvs_ia(tmp_path):
    r1 = pd.DataFrame({"cbo2002ocupação": ["766315", "784205", "141510"],
                       "descricao": ["Operador de Acabamento", "Alimentador", "Gerente de Restaurante"],
                       "macrofamilia": [OPERACAO, OPERACAO, APOIO], "nivel_qualificacao": ["Qualificado", "Básico", "Superior"],
                       "lideranca": [False, False, True], "justificativa": ["", "", "Serviço."]})
    r2 = r1.assign(macrofamilia=[TEXTIL, OPERACAO, "Alimentos e bebidas"], justificativa="")
    r1.to_csv(tmp_path / "r1.csv", index=False)
    r2.to_csv(tmp_path / "r2.csv", index=False)
    return tmp_path / "r1.csv", tmp_path / "r2.csv"


def test_mapeamento_final_aplica_o_desempate_e_sem_referencia_nao_muda(tmp_path):
    from src.cbo_ia import aplicar_mapeamento, mapeamento_final

    r1, r2 = _csvs_ia(tmp_path)
    final = mapeamento_final(r1, caminho_referencia=r2).set_index("cbo")
    assert final.loc["766315", "macrofamilia"] == TEXTIL                  # 1ª desviou do prefixo sem justificar
    assert final.loc["766315", "macrofamilia_ia"] == OPERACAO
    assert final.loc["141510", "origem"].startswith("desempate: prefixo não resolve")
    df = pd.DataFrame({"cbo2002ocupação": ["766315", "784205"]})
    assert aplicar_mapeamento(df, str(r1))["macrofamilia"].tolist() == [OPERACAO, OPERACAO]   # comportamento antigo
    assert aplicar_mapeamento(df, str(r1), caminho_referencia=r2)["macrofamilia"].tolist() == [TEXTIL, OPERACAO]


def test_auditoria_descreve_a_regra_e_conta_os_caminhos(tmp_path):
    from src.cbo_ia import mapeamento_final

    r1, r2 = _csvs_ia(tmp_path)
    texto = nar.texto_desempate(mapeamento_final(r1, caminho_referencia=r2))
    assert "regra explícita" in texto and "prefixo" in texto and "overrides.csv" in texto
    assert "1 pelo prefixo" in texto and "1 aguardando revisão manual" in texto
    assert "difere da que a IA deu em 1 CBO." in texto
