"""Motor de métricas, diagnóstico, recomendações e formatação do dashboard v2."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from dashboard import comum as c
from dashboard import narrativa as nar


def _celula(**valores) -> dict:
    """Uma linha do agregado com todas as colunas aditivas (padrão 0)."""
    linha = {col: 0 for col in c.COLUNAS_ADITIVAS}
    linha.update({
        "regiao": "Norte Catarinense", "municipio": "420910", "municipio_nome": "Joinville",
        "microrregiao": "Joinville", "setor": "Metalurgia e produtos de metal",
        "macrofamilia_cbo": "Metalmecânica e eletroeletrônica", "nivel_qualificacao": "Qualificado",
        "mes": "202509", "populacao_2026": 650_000.0, "escopo_industrial": True,
    })
    linha.update(valores)
    return linha


def _df(*linhas: dict) -> pd.DataFrame:
    return pd.DataFrame(list(linhas))


# --- Reagregação: somar antes de dividir -------------------------------------


def test_reagregacao_soma_antes_de_dividir_e_nao_promedia_razoes():
    """Uma célula com 1 desligamento não pode pesar o mesmo que uma com 1.000.

    Célula A: 1 desligamento, 1 a pedido (100%). Célula B: 1.000 desligamentos,
    100 a pedido (10%). A taxa certa é 101/1.001 ≈ 10,09%; a média das razões
    daria 55% — o defeito que este teste impede.
    """
    df = _df(_celula(desligamentos=1, desligamentos_a_pedido=1, setor="A"),
             _celula(desligamentos=1000, desligamentos_a_pedido=100, setor="B"))
    t = c.total(df)
    assert t[c.M_SAIDA_VOL] == pytest.approx(101 / 1001)
    media_de_razoes = (1 / 1 + 100 / 1000) / 2
    assert abs(t[c.M_SAIDA_VOL] - media_de_razoes) > 0.4


def test_salario_medio_e_gap_vem_de_somas_e_contagens():
    df = _df(_celula(soma_salario_admissao=60_000, n_salario_admissao=30,
                     soma_salario_desligamento=75_000, n_salario_desligamento=30),
             _celula(soma_salario_admissao=2_000, n_salario_admissao=1,
                     soma_salario_desligamento=0, n_salario_desligamento=0, setor="X"))
    t = c.total(df)
    assert t[c.M_SAL_ADM] == pytest.approx(62_000 / 31)
    assert t[c.M_SAL_DESL] == pytest.approx(2_500)
    assert t[c.M_GAP_SAL] == pytest.approx((62_000 / 31) / 2_500)


def test_populacao_soma_municipios_distintos_nunca_linhas():
    """Joinville em 3 setores e 2 meses: população conta uma vez só."""
    df = _df(*[_celula(admissoes=10, setor=s, mes=m) for s in ("A", "B", "C") for m in ("202509", "202510")],
             _celula(municipio="420540", municipio_nome="Florianópolis", populacao_2026=550_000.0, admissoes=10))
    t = c.total(df)
    assert t[c.M_POP] == 1_200_000
    assert t[c.M_SALDO_10K] == pytest.approx(70 / 1_200_000 * 10_000)


def test_agregar_por_dimensao_preserva_o_total():
    df = _df(_celula(admissoes=5, desligamentos=3, regiao="R1"),
             _celula(admissoes=2, desligamentos=7, regiao="R2", municipio="420540"))
    por = c.agregar_metricas(df, ["regiao"])
    assert por[c.M_SALDO].sum() == c.total(df)[c.M_SALDO] == -3


# --- Casos de borda ------------------------------------------------------------


def test_zero_desligamentos_deixa_saida_voluntaria_indefinida():
    t = c.total(_df(_celula(admissoes=200)))
    assert math.isnan(t[c.M_SAIDA_VOL])
    assert t[c.M_SALDO] == 200


def test_salarios_ausentes_deixam_salario_e_gap_nan():
    t = c.total(_df(_celula(admissoes=200, desligamentos=150)))
    assert math.isnan(t[c.M_SAL_ADM]) and math.isnan(t[c.M_GAP_SAL])
    assert math.isnan(t[c.M_GAP_ESC])


def test_recorte_vazio_tem_contagens_zero_e_razoes_nan():
    vazio = _df(_celula()).iloc[0:0]
    t = c.total(vazio)
    assert t[c.M_MOV] == 0 and t[c.M_SALDO] == 0
    assert math.isnan(t[c.M_SAIDA_VOL])
    rotulos = dict(c.calcular_kpis(vazio))
    assert rotulos["Saldo"] == 0.0


def test_aceleracao_por_blocos_de_12_meses_independe_do_filtro_de_periodo():
    """M5.C6: a aceleração semestral (M1.C3) não volta; volta por blocos 12 × 12."""
    assert not hasattr(c, "corte_semestral")
    df = c.anexar_blocos(_df(
        _com_estoque(mes="202410", admissoes=100, desligamentos=90),   # anterior: +10
        _com_estoque(mes="202510", admissoes=100, desligamentos=60),   # recente: +40
    ))
    so_recente = df[df["mes"].astype(str).between(*c.BLOCO_RECENTE)]
    for recorte in (df, so_recente):
        t = c.total(recorte)
        assert t[c.M_ACEL] == pytest.approx((40 - 10) / 1000 * 100)  # +3 p.p.
    # Base de 12 meses: sem bloco anterior, nada é anexado e a aceleração fica vazia.
    so12 = _df(_com_estoque(mes="202510", admissoes=10))
    assert c.anexar_blocos(so12) is so12 and math.isnan(c.total(so12)[c.M_ACEL])
    assert c.periodo_padrao([f"2024{m:02d}" for m in range(9, 13)] + [f"2025{m:02d}" for m in range(1, 13)]
                            + [f"2026{m:02d}" for m in range(1, 9)]) == ("202509", "202608")


# --- Guarda de amostra -----------------------------------------------------------


def test_guarda_de_amostra_movimentacoes_e_salarios():
    df = _df(_celula(admissoes=60, desligamentos=39, n_salario_admissao=60, soma_salario_admissao=1,
                     n_salario_desligamento=29, soma_salario_desligamento=1, setor="pequeno"),
             _celula(admissoes=70, desligamentos=40, n_salario_admissao=70, soma_salario_admissao=70,
                     n_salario_desligamento=40, soma_salario_desligamento=40, setor="grande"))
    m = c.agregar_metricas(df, ["setor"]).set_index("setor")
    assert not m.loc["pequeno", c.M_AMOSTRA_OK] and m.loc["grande", c.M_AMOSTRA_OK]
    assert math.isnan(m.loc["pequeno", c.M_GAP_SAL])
    assert m.loc["grande", c.M_GAP_SAL] == pytest.approx(1.0)
    matriz = c.matriz_diagnostico(df, ["regiao", "setor"])
    assert list(matriz["setor"]) == ["grande"]


# --- z-scores e quadrantes ----------------------------------------------------------


def test_zscore_padroniza_e_trata_constante_e_nan():
    z = c.zscore(pd.Series([1.0, 2.0, 3.0, float("nan")]))
    assert z.iloc[:3].tolist() == pytest.approx([-1.2247, 0.0, 1.2247], abs=1e-4)
    assert math.isnan(z.iloc[3])
    assert c.zscore(pd.Series([5.0, 5.0])).tolist() == [0.0, 0.0]


@pytest.mark.parametrize(("dinamismo", "tensao", "esperado"), [
    (1, 1, c.Q_PRESSAO), (1, -1, c.Q_SAUDAVEL), (-1, 1, c.Q_APAGAO), (-1, -1, c.Q_ESTAGNACAO), (0, 0, c.Q_PRESSAO),
])
def test_quadrantes(dinamismo, tensao, esperado):
    assert c.quadrante(dinamismo, tensao) == esperado


def test_matriz_aponta_o_motor_da_tensao():
    base = dict(n_salario_admissao=50, n_salario_desligamento=50,
                soma_salario_admissao=100_000, soma_salario_desligamento=100_000)
    df = _df(_celula(setor="calmo", admissoes=100, desligamentos=100, desligamentos_a_pedido=10, **base),
             _celula(setor="medio", admissoes=100, desligamentos=100, desligamentos_a_pedido=30, **base),
             _celula(setor="tenso", admissoes=100, desligamentos=100, desligamentos_a_pedido=90, **base))
    m = c.matriz_diagnostico(df, ["regiao", "setor"])
    assert m.iloc[0]["setor"] == "tenso"
    assert m.iloc[0]["motor"] == "saída voluntária alta"


def test_tensao_usa_so_sintomas_e_ignora_a_compressao_salarial():
    """M1.C1: a compressão é causa (selo Salarial), não entra na tensão."""
    df = _df(_celula(setor="comprimido", admissoes=100, desligamentos=100, desligamentos_a_pedido=30,
                     **_salarios(1000, 2000)),
             _celula(setor="pede_conta", admissoes=100, desligamentos=100, desligamentos_a_pedido=60,
                     **_salarios(2000, 2000)))
    m = c.matriz_diagnostico(df, ["regiao", "setor"])
    assert m.iloc[0]["setor"] == "pede_conta"
    assert "z_compressao" not in m.columns
    assert m["tensao"].tolist() == pytest.approx(m[f"z_{c.M_SAIDA_VOL}"].tolist())


# --- Regras de recomendação -----------------------------------------------------------


def _salarios(adm: float, desl: float, n: int = 50) -> dict:
    return dict(soma_salario_admissao=adm * n, n_salario_admissao=n,
                soma_salario_desligamento=desl * n, n_salario_desligamento=n)


def _referencia(regiao: str = "Serrana", municipio: str = "420300") -> dict:
    """Unidade neutra que puxa a referência do recorte para 30% de saída voluntária."""
    return _celula(regiao=regiao, municipio=municipio, macrofamilia_cbo="Referência",
                   admissoes=1000, desligamentos=1000, desligamentos_a_pedido=300, **_salarios(2000, 2000))


def _alavancas(df: pd.DataFrame, regiao: str = "Norte Catarinense") -> set[str]:
    return {r.alavanca for r in c.gerar_recomendacoes(df) if r.regiao == regiao}


def test_regra_salarial_compressao_e_saida_voluntaria_alta():
    df = _df(_referencia(), _celula(admissoes=200, desligamentos=200, desligamentos_a_pedido=120,
                                    **_salarios(1800, 2000)))
    assert c.ALAVANCA_SALARIO in _alavancas(df)


def test_regra_formacao_gap_de_escolaridade_negativo_em_familia_tecnica():
    df = _df(_referencia(), _celula(admissoes=200, desligamentos=200, desligamentos_a_pedido=60,
                                    nivel_qualificacao="Técnico", **_salarios(2000, 2000),
                                    soma_escolaridade_admissao=8 * 200, n_escolaridade_admissao=200,
                                    soma_escolaridade_desligamento=9 * 200, n_escolaridade_desligamento=200))
    assert c.ALAVANCA_FORMACAO in _alavancas(df)


def test_regra_mobilidade_expansao_sob_pressao_e_retracao_noutra_regiao():
    macro = "Metalmecânica e eletroeletrônica"
    df = _df(
        _referencia(),
        # Norte: expansão (saldo +150) com alta saída voluntária e compressão.
        _celula(admissoes=400, desligamentos=250, desligamentos_a_pedido=200, **_salarios(1700, 2000)),
        # Sul: mesma macrofamília em retração.
        _celula(regiao="Sul Catarinense", municipio="420460", admissoes=100, desligamentos=300,
                desligamentos_a_pedido=30, macrofamilia_cbo=macro, **_salarios(2000, 2000)),
    )
    recs = [r for r in c.gerar_recomendacoes(df) if r.alavanca == c.ALAVANCA_MOBILIDADE]
    assert recs and recs[0].regiao == "Norte Catarinense"
    assert recs[0].extras["origem"] == "Sul Catarinense"


def test_regra_automacao_basico_e_saldo_nao_positivo():
    df = _df(
        _celula(regiao="Serrana", municipio="420300", macrofamilia_cbo="Referência",
                admissoes=1000, desligamentos=700, desligamentos_a_pedido=200, **_salarios(2000, 2000)),
        _celula(admissoes=300, desligamentos=300, desligamentos_a_pedido=60, nivel_qualificacao="Básico",
                **_salarios(2000, 2000)),
    )
    assert c.ALAVANCA_AUTOMACAO in _alavancas(df)


def test_regra_retencao_saida_voluntaria_alta_sem_compressao():
    df = _df(_referencia(), _celula(admissoes=200, desligamentos=200, desligamentos_a_pedido=120,
                                    **_salarios(2100, 2000)))
    alavancas = _alavancas(df)
    assert c.ALAVANCA_RETENCAO in alavancas and c.ALAVANCA_SALARIO not in alavancas


def test_regras_respeitam_a_guarda_de_amostra():
    df = _df(_referencia(), _celula(admissoes=40, desligamentos=40, desligamentos_a_pedido=40,
                                    **_salarios(1000, 2000, n=40)))
    assert _alavancas(df) == set()


def test_causas_selam_salarial_qualificacao_e_retencao():
    linha = pd.Series({c.M_GAP_SAL: 0.9, c.M_GAP_ESC: -0.3, c.M_SAIDA_VOL: 0.6})
    assert c.causas(linha, saida_ref=0.47, fracao_tecnica=0.6) == [c.CAUSA_SALARIAL, c.CAUSA_QUALIFICACAO]
    linha = pd.Series({c.M_GAP_SAL: 1.05, c.M_GAP_ESC: 0.1, c.M_SAIDA_VOL: 0.6})
    assert c.causas(linha, saida_ref=0.47) == [c.CAUSA_RETENCAO]


# --- Formatação pt-BR ------------------------------------------------------------------


@pytest.mark.parametrize(("funcao", "valor", "esperado"), [
    (c.fmt_num, 1234.5, "1.234"), (lambda v: c.fmt_num(v, 1), 1234.5, "1.234,5"),
    (c.fmt_pct, 0.471, "47,1%"), (c.fmt_brl, 2345.4, "R$ 2.345"), (c.fmt_razao, 0.951, "0,95"),
    (c.fmt_int, -2645, "−2.645"), (c.fmt_pp, 4.25, "+4,2 p.p."), (c.fmt_pct, float("nan"), "—"),
    (c.rotulo_mes, "202509", "set/25"),
])
def test_formatacao_ptbr(funcao, valor, esperado):
    assert funcao(valor) == esperado


def test_delta_usa_ascii_para_o_sinal_que_o_streamlit_interpreta():
    assert c.delta_texto(c.M_SAIDA_VOL, 0.50, 0.47, "vs estado") == "+3,0 p.p. vs estado"
    assert c.delta_texto(c.M_GAP_SAL, 0.90, 0.95, "vs estado") == "-5 p.p. vs estado"


# --- Narrativa ---------------------------------------------------------------------------


def test_resposta_principal_usa_os_numeros_do_recorte():
    df = _df(_celula(admissoes=600, desligamentos=400, desligamentos_a_pedido=200))
    frase = nar.resposta_principal(df)
    assert "1.000 movimentações" in frase and "saldo de 200" in frase and "50,0%" in frase


def test_filtro_v2_por_escopo_territorio_e_nivel():
    df = _df(_celula(admissoes=1), _celula(admissoes=2, escopo_industrial=False, setor="Comércio"),
             _celula(admissoes=4, regiao="Serrana", nivel_qualificacao="Básico"))
    assert c.filtrar(df, c.Filtros())["admissoes"].sum() == 5
    assert c.filtrar(df, c.Filtros(escopo=c.ESCOPO_ECONOMIA))["admissoes"].sum() == 7
    assert c.filtrar(df, c.Filtros(territorios=("Serrana",)))["admissoes"].sum() == 4
    assert c.filtrar(df, c.Filtros(niveis=("Qualificado",)))["admissoes"].sum() == 1


# --- Estoque da RAIS (M4.C5) -------------------------------------------------


def _com_estoque(**valores) -> dict:
    base = {"secao_industrial": "Indústrias de Transformação", "estoque_31dez": 1000,
            "estoque_escolaridade_informada": 1000, "estoque_medio_ou_mais": 600,
            "desligados_rais": 200, "desligados_precoce": 140}
    base.update(valores)
    return _celula(**base)


def test_estoque_entra_uma_vez_por_celula_e_nao_por_mes():
    # Mesma célula em dois meses: o estoque (1000) não pode virar 2000.
    df = _df(_com_estoque(mes="202509", admissoes=150, desligamentos=120, desligamentos_descontados=80),
             _com_estoque(mes="202510", admissoes=50, desligamentos=60, desligamentos_descontados=40))
    t = c.total(df)
    assert t[c.M_ESTOQUE] == 1000
    assert t[c.M_ROT_DESC] == pytest.approx(min(200, 120) / 1000)
    assert t[c.M_VAR_REL] == pytest.approx((200 - 180) / 1000)
    assert t[c.M_PRECOCE] == pytest.approx(0.7)
    # Duas células distintas somam os estoques.
    outra = _com_estoque(municipio="420540", municipio_nome="Florianópolis", estoque_31dez=500,
                         admissoes=10, desligamentos_descontados=10)
    assert c.total(_df(*df.to_dict("records"), outra))[c.M_ESTOQUE] == 1500


def test_sem_estoque_as_metricas_da_rais_ficam_vazias():
    t = c.total(_df(_celula(admissoes=10, desligamentos=5)))
    assert math.isnan(t[c.M_ROT_DESC]) and math.isnan(t[c.M_PRECOCE])


def test_anexar_estoque_casa_pela_celula():
    agregado = _df(_com_estoque(), _com_estoque(mes="202510")).drop(columns=c.COLUNAS_ESTOQUE)
    estoque = _df(_com_estoque())[c.CHAVES_ESTOQUE + c.COLUNAS_ESTOQUE]
    avisos: list[str] = []
    junto = c.anexar_estoque(agregado, estoque, avisos)
    assert list(junto["estoque_31dez"]) == [1000, 1000] and not avisos
    assert c.anexar_estoque(agregado, None, avisos) is agregado and avisos


def test_tensao_tem_os_tres_sintomas_e_dinamismo_usa_o_estoque():
    assert set(c.PESOS_TENSAO_PADRAO) == {c.M_ROT_DESC, c.M_SAIDA_VOL, c.M_PRECOCE}
    comum = dict(admissoes=100, desligamentos=100, desligamentos_a_pedido=40)
    df = _df(
        _com_estoque(setor="calmo", desligamentos_descontados=20, desligados_precoce=40, **comum),
        _com_estoque(setor="medio", desligamentos_descontados=50, desligados_precoce=100, **comum),
        _com_estoque(setor="tenso", desligamentos_descontados=90, desligados_precoce=180, **comum),
    )
    m = c.matriz_diagnostico(df, [c.COLUNA_SETOR]).set_index(c.COLUNA_SETOR)
    # Saída voluntária igual: quem ordena é rotatividade + precoce.
    assert list(m.index) == ["tenso", "medio", "calmo"]
    assert m.loc["tenso", "motor"] in {"rotatividade alta", "desligamento precoce alto"}


def test_dinamismo_cai_para_o_saldo_relativo_sem_estoque():
    df = _df(_celula(setor="a", admissoes=200, desligamentos=100),
             _celula(setor="b", admissoes=100, desligamentos=200))
    m = c.matriz_diagnostico(df, [c.COLUNA_SETOR]).set_index(c.COLUNA_SETOR)
    assert m.loc["a", "dinamismo"] > 0 > m.loc["b", "dinamismo"]


# --- DATA-01: nota do gap de escolaridade fora da curva ----------------------

def _esc(macro: str, regiao: str, municipio: str, adm: int, esc_adm: float, desl: int, esc_desl: float) -> dict:
    return _celula(macrofamilia_cbo=macro, regiao=regiao, municipio_nome=municipio,
                   admissoes=adm, desligamentos=desl,
                   soma_escolaridade_admissao=adm * esc_adm, n_escolaridade_admissao=adm,
                   soma_escolaridade_desligamento=desl * esc_desl, n_escolaridade_desligamento=desl)


def test_destaque_escolaridade_aponta_onde_o_gap_se_concentra():
    df = _df(
        _esc("Alimentos e bebidas", "Oeste Catarinense", "Chapecó", 300, 4.5, 300, 5.5),
        _esc("Alimentos e bebidas", "Serrana", "Lages", 100, 6.0, 100, 6.0),
        _esc("Têxtil, confecção, couro e calçados", "Vale do Itajaí", "Blumenau", 200, 6.3, 200, 6.3),
    )
    texto = nar.destaque_escolaridade(df)
    assert texto is not None
    assert "Alimentos e bebidas" in texto and "Oeste Catarinense" in texto and "Chapecó" in texto
    assert "0,75" in texto       # gap da macrofamília: 4,875 − 5,625
    assert "75%" in texto        # 300 de 400 admissões no Oeste


def test_destaque_escolaridade_some_quando_nada_passa_do_limiar():
    df = _df(
        _esc("Alimentos e bebidas", "Oeste Catarinense", "Chapecó", 300, 5.4, 300, 5.5),
        _esc("Têxtil, confecção, couro e calçados", "Vale do Itajaí", "Blumenau", 200, 6.3, 200, 6.3),
    )
    assert nar.destaque_escolaridade(df) is None
    assert nar.destaque_escolaridade(df.iloc[0:0]) is None


# --- BUG-01: absoluto de território nunca se compara com o absoluto do estado --

@pytest.mark.parametrize("nome", sorted(c.METRICAS_ABSOLUTAS))
def test_delta_recusa_metricas_absolutas(nome):
    assert c.delta_texto(nome, -1913, 2726, "vs estado") is None


def test_delta_continua_em_taxas_e_razoes():
    assert c.delta_texto(c.M_SALDO_10K, 5.0, 2.0, "vs estado") == "+3,0 vs estado"
    assert c.delta_texto(c.M_ROT_DESC, 0.30, 0.336, "vs SC") == "-3,6 p.p. vs SC"


def test_participacao_estadual_no_mesmo_sinal_e_com_sinais_opostos():
    assert c.participacao_estadual(c.M_SALDO, 1000, 2726) == "36,7% do saldo estadual"
    assert c.participacao_estadual(c.M_MOV, 50, 200) == "25,0% das movimentações do estado"
    # Grande Florianópolis fechou vagas e o estado abriu: fração negativa não tem leitura.
    assert c.participacao_estadual(c.M_SALDO, -1913, 2726) == "estado: 2.726"
    assert c.participacao_estadual(c.M_SALDO, 0, 2726) == "0,0% do saldo estadual"
    assert c.participacao_estadual(c.M_SALDO, 10, 0) is None
    assert c.participacao_estadual(c.M_SAIDA_VOL, 0.5, 0.4) is None  # taxa: usa delta_texto
