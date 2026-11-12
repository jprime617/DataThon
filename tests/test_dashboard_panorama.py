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
