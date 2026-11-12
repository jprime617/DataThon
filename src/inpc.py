"""INPC mensal do SIDRA e fator de deflação para preços de ago/2026 (M5.C2).

`python -m src.inpc` busca a tabela 1736, variável 44 (INPC, variação mensal %)
e grava `data_processed/inpc.csv`, versionado, para o pipeline rodar offline.
O fator de cada competência leva o valor nominal a preços de 202608:
fator_t = índice_202608 ÷ índice_t (fator de 202608 = 1).
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_INPC = RAIZ / "data_processed" / "inpc.csv"
URL = "https://apisidra.ibge.gov.br/values/t/1736/n1/all/v/44/p/{inicio}-{fim}"
INICIO, BASE = 202409, 202608


def fatores(variacao: pd.Series) -> pd.Series:
    """Variação mensal (%) indexada por AAAAMM → fator para preços do último mês."""
    indice = (1 + variacao.sort_index() / 100).cumprod()
    return indice.iloc[-1] / indice


def baixar_inpc(inicio: int = INICIO, fim: int = BASE, destino: Path = CAMINHO_INPC) -> pd.DataFrame:
    with urllib.request.urlopen(URL.format(inicio=inicio, fim=fim), timeout=60) as r:
        linhas = json.load(r)[1:]  # a primeira linha é o cabeçalho
    variacao = pd.Series({int(l["D3C"]): float(l["V"]) for l in linhas})
    df = pd.DataFrame({
        "competencia": variacao.index,
        "inpc_variacao_pct": variacao.values,
        "fator_ago2026": fatores(variacao).values,
    })
    if df.empty or df["competencia"].min() != inicio or df["competencia"].max() != fim:
        raise RuntimeError(f"SIDRA não trouxe o INPC de {inicio} a {fim}")
    df.to_csv(destino, index=False)
    return df


if __name__ == "__main__":
    print(baixar_inpc().to_string(index=False))
