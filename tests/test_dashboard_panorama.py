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
