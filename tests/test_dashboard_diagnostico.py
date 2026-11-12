"""M3.C1: o "por quê" de cada cartão de alerta, numa frase sem jargão."""

import pandas as pd

from dashboard import comum as c
from dashboard.paginas.diagnostico import frase_porque


def _u(saida: float, gap: float) -> pd.Series:
    return pd.Series({c.M_SAIDA_VOL: saida, c.M_GAP_SAL: gap})


def test_frase_prioriza_a_causa_salarial():
    assert frase_porque(_u(0.6, 0.87), [c.CAUSA_SALARIAL], 0.47).startswith("Quem entra ganha 87%")


def test_frase_de_retencao_compara_com_o_estado():
    frase = frase_porque(_u(0.6, 1.02), [c.CAUSA_RETENCAO], 0.47)
    assert "60%" in frase and "estado: 47%" in frase and "reter" in frase


def test_frase_sem_causa_nao_inventa_explicacao():
    assert "nenhuma causa isolada" in frase_porque(_u(0.5, 0.97), [], 0.47)


def test_matriz_legivel_so_cor_e_eixos_em_palavras():
    """M3.C2: sem os 4 símbolos e sem z-score na tela."""
    from dashboard import figuras as fig

    m = pd.DataFrame({"dinamismo": [1.0, -1.0], "tensao": [1.0, -1.0], c.M_MOV: [500, 300],
                      c.M_SAIDA_VOL: [0.6, 0.3], c.M_GAP_SAL: [0.9, 1.0], "motor": ["a", "b"],
                      "quadrante": [c.Q_PRESSAO, c.Q_ESTAGNACAO]})
    figura = fig.construir_matriz(m, pd.Series(["x", "y"]))
    assert all(t.marker.symbol is None for t in figura.data)
    eixos = f"{figura.layout.xaxis.title.text} {figura.layout.yaxis.title.text}"
    assert "cresce" in eixos and "equipe" in eixos and "z" not in eixos.replace("cresce", "")
    assert figura.layout.xaxis.showticklabels is False


def test_gap_salarial_em_palavras():
    """M3.C3: "gap 0,94" vira "6% abaixo"."""
    assert c.fmt_gap(0.94) == "6% abaixo"
    assert c.fmt_gap(1.03) == "3% acima"
    assert c.fmt_gap(float("nan")) == "—"
    assert c.fmt_metrica(c.M_GAP_SAL, 0.94) == "6% abaixo"


def test_no_maximo_quatro_indicadores_principais():
    assert len(c.KPIS_PADRAO) <= 4


def test_no_maximo_dois_graficos_a_vista_por_pagina():
    """M3.C4: gráficos além de 2 ficam dentro de um expander ("Aprofundar")."""
    import ast
    from pathlib import Path

    for arquivo in (Path(__file__).parent.parent / "dashboard" / "paginas").glob("*.py"):
        if arquivo.stem in ("apresentacao", "__init__"):  # apresentação: um gráfico por slide
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        dentro = {id(n) for w in ast.walk(arvore) if isinstance(w, ast.With)
                  and any("expander" in ast.unparse(i.context_expr) for i in w.items)
                  for n in ast.walk(w)}
        a_vista = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
                   and ast.unparse(n.func).endswith(("plotly_chart", "graphviz_chart")) and id(n) not in dentro]
        assert len(a_vista) <= 2, f"{arquivo.name}: {len(a_vista)} gráficos à vista"


def test_metodologia_cobre_r1_a_r9_e_r7_4_tem_grafico():
    """M3.C7: tabela requisito → onde aparece, e o R7.4 existe de fato."""
    import inspect

    from dashboard.paginas import causa_raiz, metodologia

    ids = " ".join(r for r, _, _ in metodologia.REQUISITOS)
    assert all(f"R{i}" in ids for i in range(1, 10))
    assert "c.M_ESC_ADM, c.M_SAL_ADM" in inspect.getsource(causa_raiz.render)


def test_sem_causa_isolada_cita_o_sintoma_que_mais_puxa_a_tensao():
    u = pd.Series({c.M_SAIDA_VOL: 0.40, c.M_GAP_SAL: 0.98, c.M_ROT_DESC: 0.64, c.M_PRECOCE: 0.80,
                   "z_" + c.M_SAIDA_VOL: -0.5, "z_" + c.M_ROT_DESC: 2.1, "z_" + c.M_PRECOCE: 1.0})
    ref = pd.Series({c.M_SAIDA_VOL: 0.48, c.M_ROT_DESC: 0.32, c.M_PRECOCE: 0.69})
    frase = frase_porque(u, [], 0.48, ref)
    assert frase.startswith("Rotatividade descontada: 64%, acima dos 32%")
