"""Achado ativo no Panorama: o botão vira "Voltar ao estado" só no recorte exato do achado."""

from dashboard.paginas.panorama import achado_ativo


def test_achado_ativo_exige_o_recorte_exato():
    filtros = {"f_macro": ["Alimentos e bebidas"]}
    assert achado_ativo(filtros, {"f_macro": ["Alimentos e bebidas"], "f_terr": []})
    assert not achado_ativo(filtros, {"f_macro": ["Alimentos e bebidas"], "f_setor": ["Têxtil"]})
    assert not achado_ativo(filtros, {})


def test_achado_de_unidade_confere_o_nivel_territorial():
    filtros = {"f_nivel": "Mesorregião", "f_terr": ["Oeste Catarinense"], "f_setor": ["Têxtil"]}
    estado = {"f_nivel": "Mesorregião", "f_terr": ["Oeste Catarinense"], "f_setor": ["Têxtil"]}
    assert achado_ativo(filtros, estado)
    assert not achado_ativo(filtros, {**estado, "f_nivel": "Microrregião"})


def test_ranking_de_secoes_ordena_por_saldo_com_saida_voluntaria():
    """R7.3 (M3.C6): seções em ordem decrescente de saldo, saída voluntária ao lado."""
    import math

    import pandas as pd

    from dashboard import comum as c
    from dashboard.paginas.panorama import ranking_secoes

    base = {col: 0 for col in c.COLUNAS_ADITIVAS}
    df = pd.DataFrame([
        {**base, c.COLUNA_SECAO_INDUSTRIAL: "Construção", "admissoes": 100, "desligamentos": 150,
         "desligamentos_a_pedido": 60},
        {**base, c.COLUNA_SECAO_INDUSTRIAL: "Transformação", "admissoes": 300, "desligamentos": 200,
         "desligamentos_a_pedido": 100},
        {**base, c.COLUNA_SECAO_INDUSTRIAL: "Extrativas", "admissoes": 10, "desligamentos": 5,
         "desligamentos_a_pedido": 1},
    ])
    r = ranking_secoes(df)
    assert list(r["Seção (CNAE)"]) == ["Transformação", "Extrativas", "Construção"]
    assert list(r["Saldo de vagas"]) == [100, 5, -50]
    assert r["Saída voluntária"].iloc[0] == 0.5 and math.isnan(r["Saída voluntária"].iloc[1])


# --- Mapa: clicar seleciona, não navega -------------------------------------------


def test_clique_no_mapa_seleciona_o_territorio_sem_abrir_a_ficha():
    """Regressão: soltar o mouse depois de arrastar o mapa abria a ficha; agora só seleciona."""
    from dashboard.paginas.panorama import atualizar_selecao

    sessao = {}
    atualizar_selecao({"selection": {"points": [{"customdata": ["Blumenau"]}]}}, "Município", sessao)
    assert sessao["mapa_sel"] == ("Município", "Blumenau") and "ficha_alvo" not in sessao


def test_selecao_limpa_nao_volta_com_o_mesmo_clique_nos_reruns():
    from dashboard.paginas.panorama import atualizar_selecao

    clique = {"selection": {"points": [{"customdata": "Joinville"}]}}
    sessao = {}
    atualizar_selecao(clique, "Município", sessao)
    sessao["mapa_sel"] = None  # botão "Limpar seleção"
    atualizar_selecao(clique, "Município", sessao)  # o gráfico ainda guarda o mesmo clique
    assert sessao["mapa_sel"] is None
    atualizar_selecao({"selection": {"points": []}}, "Município", sessao)
    atualizar_selecao(clique, "Município", sessao)  # clicar de novo seleciona de novo
    assert sessao["mapa_sel"] == ("Município", "Joinville")


# --- Legenda lateral, sinais e guia de decisão ----------------------------------------


def _unidades(valores, mov=None):
    import pandas as pd

    from dashboard import comum as c

    mov = mov or [500] * len(valores)
    return pd.DataFrame({"rotulo": [f"U{i}" for i in range(len(valores))], c.M_SAIDA_VOL: valores,
                         c.M_MOV: mov, c.M_AMOSTRA_OK: [m >= c.MIN_MOVIMENTACOES for m in mov]})


def test_legenda_lateral_vai_do_maior_ao_menor_e_conta_as_unidades():
    from dashboard import comum as c
    from dashboard import figuras as fig

    itens = fig.faixas_legenda(_unidades([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]), c.M_SAIDA_VOL, "rotulo")
    assert [f for _, f, _ in itens][0].startswith("acima de") and itens[-1][1].startswith("até")
    assert sum(n for *_, n in itens) == 8
    assert [cor for cor, *_ in itens] == fig.PALETAS_MAPA[c.M_SAIDA_VOL][::-1]


def test_extremos_do_mapa_respeitam_o_sentido_do_indicador_e_a_amostra():
    from dashboard import comum as c
    from dashboard import narrativa as nar

    df = _unidades([0.2, 0.9, 0.5, 0.99], mov=[500, 500, 500, 10])
    piores, melhores = nar.extremos_mapa(df, c.M_SAIDA_VOL, "rotulo", n=1)
    assert piores[0][0] == "U1" and melhores[0][0] == "U0"  # U3 tem poucos dados


def test_sinais_usam_referencia_fixa_sem_recorte_e_o_estado_com_recorte():
    import pandas as pd

    from dashboard import comum as c
    from dashboard import narrativa as nar

    t = pd.Series({c.M_SALDO: 100, c.M_MOV: 10_000, c.M_SALDO_REL: 0.01, c.M_SALDO_10K: 1.0,
                   c.M_ROT_DESC: 0.30, c.M_SAIDA_VOL: 0.45, c.M_GAP_SAL: 0.90, c.M_SALARIO_OK: True})
    saldo, rot, saida, gap = nar.sinais(t)
    assert saldo.alerta and "100 contratações e saídas para cada vaga nova" in saldo.leitura
    assert not rot.alerta and "Oficial (MTE)" in rot.referencia  # 30% < 33,6% (SC)
    assert saida.alerta and gap.alerta  # 45% ≥ 40%; 10% abaixo
    ref = t.copy()
    ref[c.M_SAIDA_VOL] = 0.42
    assert not nar.sinais(t, ref)[2].alerta  # 45% < 42% + 5 p.p.


def test_resumo_dos_quadrantes_soma_todas_as_movimentacoes():
    import pandas as pd

    from dashboard import comum as c
    from dashboard import narrativa as nar

    m = pd.DataFrame({"quadrante": [c.Q_APAGAO, c.Q_APAGAO, c.Q_SAUDAVEL], c.M_MOV: [100, 300, 600]})
    r = nar.resumo_quadrantes(m)
    assert r[c.Q_APAGAO] == (2, 0.4) and r[c.Q_PRESSAO] == (0, 0.0)
    assert sum(f for _, f in r.values()) == 1.0
