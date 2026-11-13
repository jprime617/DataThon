"""TAX-01: abre o setor "Veículos" (CNAE div. 29 + 30) por divisão, subclasse e município.

Lê os `.7z` do Novo CAGED baixados por `src.download` (MOV + FOR − EXC, mesma
regra de peso de `src.caged24`), guarda só as linhas de SC nas divisões 29 e 30
e grava um resumo pequeno e versionável em
`data_processed/veiculos_por_divisao.csv` (município × divisão × subclasse ×
mês: admissões, desligamentos e saldo).

Uso::

    python -m scripts.veiculos_por_divisao
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.caged24 import PESO, UF_SC, _comando  # noqa: E402
from src.download import DESTINO as DIR_7Z, FIM, INICIO, TIPOS, competencias  # noqa: E402

DIVISOES = {29: "Veículos automotores", 30: "Outros equipamentos de transporte (inclui naval)"}
CACHE = RAIZ / "data" / "interim" / "veiculos"
DESTINO = RAIZ / "data_processed" / "veiculos_por_divisao.csv"
COLUNAS = ["competênciamov", "uf", "município", "seção", "subclasse", "saldomovimentação"]


def _ler(arquivo: Path, tipo: str) -> pd.DataFrame:
    import subprocess

    proc = subprocess.Popen(_comando(arquivo), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    blocos = []
    try:
        for bloco in pd.read_csv(proc.stdout, sep=";", dtype=str, usecols=COLUNAS, chunksize=500_000):
            comp = pd.to_numeric(bloco["competênciamov"], errors="coerce")
            div = pd.to_numeric(bloco["subclasse"], errors="coerce") // 100_000
            blocos.append(bloco[(bloco["uf"].str.strip() == UF_SC) & comp.between(INICIO, FIM) & div.isin(DIVISOES)])
    finally:
        proc.stdout.close()
        if proc.wait() != 0:
            raise RuntimeError(f"falha ao descompactar {arquivo}")
    df = pd.concat(blocos, ignore_index=True)
    df["peso"] = PESO[tipo]
    return df


def consolidar() -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    partes, faltando = [], []
    for c in competencias():
        for tipo in TIPOS:
            arquivo = DIR_7Z / f"CAGED{tipo}{c}.7z"
            cache = CACHE / f"{tipo}{c}.parquet"
            if cache.exists():
                partes.append(pd.read_parquet(cache))
            elif arquivo.exists():
                df = _ler(arquivo, tipo)
                df.to_parquet(cache, index=False)
                partes.append(df)
            else:
                faltando.append(arquivo.name)
    if faltando:
        print(f"[!] {len(faltando)} arquivo(s) ausente(s): {', '.join(faltando[:5])}...", flush=True)
    df = pd.concat(partes, ignore_index=True)
    mov = pd.to_numeric(df["saldomovimentação"])
    df["admissoes"] = (mov == 1).astype(int) * df["peso"]
    df["desligamentos"] = (mov == -1).astype(int) * df["peso"]
    df["divisao"] = pd.to_numeric(df["subclasse"]) // 100_000
    df["municipio"] = df["município"].str.strip()
    resumo = (df.groupby(["municipio", "divisao", "subclasse", "competênciamov"])[["admissoes", "desligamentos"]]
              .sum().reset_index().rename(columns={"competênciamov": "mes"}))
    resumo["saldo"] = resumo["admissoes"] - resumo["desligamentos"]
    resumo = resumo[(resumo["admissoes"] != 0) | (resumo["desligamentos"] != 0)]
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    resumo.to_csv(DESTINO, index=False)
    return resumo


if __name__ == "__main__":
    r = consolidar()
    print(r.groupby("divisao")[["admissoes", "desligamentos", "saldo"]].sum())
