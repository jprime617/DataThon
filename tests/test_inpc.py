import pandas as pd

from src.inpc import fatores
from src.limpeza import CAMINHO_INPC, deflacionar_salario


def test_fator_do_mes_base_e_1_e_acumula_a_inflacao():
    f = fatores(pd.Series({202606: 1.0, 202607: 2.0, 202608: 0.0}))
    assert f[202608] == 1.0 and abs(f[202607] - 1.0) < 1e-12
    assert abs(f[202606] - 1.02) < 1e-12


def test_inpc_versionado_cobre_a_janela_e_deflaciona():
    inpc = pd.read_csv(CAMINHO_INPC)
    assert inpc.competencia.min() == 202409 and inpc.competencia.max() == 202608
    assert inpc.set_index("competencia").loc[202608, "fator_ago2026"] == 1.0
    df = pd.DataFrame({"competênciamov": [202608, 202409, 199901], "salário": [1000.0, 1000.0, 1000.0]})
    s = deflacionar_salario(df)["salário"]
    assert s[0] == 1000.0 and s[1] > 1080 and s[2] == 1000.0
