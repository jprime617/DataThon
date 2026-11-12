"""Lê o Novo CAGED de 24 meses (MOV + FOR − EXC) e consolida SC (M5.C3).

Cada `.7z` baixado por `src.download` é descompactado para a saída padrão
(`7z e -so`, ou `bsdtar -xOf` sem 7z) e lido em blocos: nenhum `.txt` vai para o
disco. Ficam só as linhas de SC (`uf == 42`) com `competênciamov` na janela.

A coluna `peso` vale +1 para MOV e FOR e −1 para EXC (a exclusão anula uma
declaração já contada). Admissões e desligamentos são a soma de `peso` por tipo,
e o saldo é Σ `peso × saldomovimentação`.

Uso::

    python -m src.caged24   # grava data/interim/caged_sc_24m.parquet
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pandas as pd

from src.download import DESTINO as DIR_7Z, FIM, INICIO, TIPOS, competencias
from src.logging_pipeline import log_etapa

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "interim" / "caged_sc_24m.parquet"
PESO = {"MOV": 1, "FOR": 1, "EXC": -1}
UF_SC = "42"
# Colunas só do EXC: descartadas para os três tipos terem o mesmo schema.
SO_EXC = ["competênciaexc", "indicadordeexclusão"]


def _comando(arquivo: Path) -> list[str]:
    if shutil.which("7z"):
        return ["7z", "e", "-so", str(arquivo)]
    return ["bsdtar", "-xOf", str(arquivo)]


def ler_arquivo(arquivo: Path, tipo: str, inicio: int = INICIO, fim: int = FIM, chunksize: int = 500_000) -> pd.DataFrame:
    """Um `.7z` do CAGED → linhas de SC na janela, como texto, com `peso`."""
    proc = subprocess.Popen(_comando(arquivo), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    blocos = []
    try:
        for bloco in pd.read_csv(proc.stdout, sep=";", dtype=str, encoding="utf-8", chunksize=chunksize):
            comp = pd.to_numeric(bloco["competênciamov"], errors="coerce")
            bloco = bloco[(bloco["uf"].str.strip() == UF_SC) & comp.between(inicio, fim)]
            blocos.append(bloco.drop(columns=[c for c in SO_EXC if c in bloco.columns]))
    finally:
        proc.stdout.close()
        if proc.wait() != 0:
            raise RuntimeError(f"falha ao descompactar {arquivo}")
    df = pd.concat(blocos, ignore_index=True)
    df["peso"] = pd.Series(PESO[tipo], index=df.index, dtype="int8")
    df["tipo_arquivo"] = tipo
    return df


def consolidar(diretorio: Path = DIR_7Z, destino: Path | None = DESTINO, inicio: int = INICIO, fim: int = FIM) -> pd.DataFrame:
    partes = []
    for c in competencias(inicio, fim):
        for tipo in TIPOS:
            arquivo = diretorio / f"CAGED{tipo}{c}.7z"
            if not arquivo.exists():
                raise FileNotFoundError(f"{arquivo} ausente: rode `python -m src.download`")
            partes.append(ler_arquivo(arquivo, tipo, inicio, fim))
    df = pd.concat(partes, ignore_index=True)
    if destino is not None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(destino, index=False)
    mov = pd.to_numeric(df["saldomovimentação"])
    log_etapa(
        "caged24",
        f"{len(df):,} linhas de SC ({df.groupby('tipo_arquivo').size().to_dict()}); "
        f"adm {df.peso[mov == 1].sum():,}, desl {df.peso[mov == -1].sum():,}",
    )
    return df


BASE_FORNECIDA = RAIZ / "Dados" / "Novo_Caged_MOV_Limpo.csv"
DESTINO_VALIDACAO = RAIZ / "data_processed" / "validacao_base_fornecida.csv"
BLOCO_RECENTE = (202509, 202608)
_CHAVE = ["competênciamov", "município"]


def _contar(df: pd.DataFrame, peso: pd.Series | None = None) -> pd.DataFrame:
    """adm/desl por mês × município; com `peso`, soma o peso em vez de contar."""
    mov = pd.to_numeric(df["saldomovimentação"])
    p = pd.Series(1, index=df.index) if peso is None else peso.astype(int)
    return pd.DataFrame({
        "competênciamov": df["competênciamov"].astype(int),
        "município": df["município"].astype(str).str.strip(),
        "adm": p.where(mov == 1, 0),
        "desl": p.where(mov == -1, 0),
    }).groupby(_CHAVE).sum()


def comparar_com_base(consolidado: pd.DataFrame, base: pd.DataFrame, bloco: tuple[int, int] = BLOCO_RECENTE) -> pd.DataFrame:
    """Base fornecida × só MOV × MOV + FOR − EXC, por mês × município (M5.C4).

    Colunas `adm_base`, `desl_base`, `adm_mov`, `desl_mov`, `adm_mfe`, `desl_mfe`;
    célula ausente de um lado conta 0.
    """
    no_bloco = lambda d: d[pd.to_numeric(d["competênciamov"]).between(*bloco)]
    c, base = no_bloco(consolidado), no_bloco(base)
    so_mov = c[c["tipo_arquivo"] == "MOV"]
    return (
        _contar(base).add_suffix("_base")
        .join(_contar(so_mov).add_suffix("_mov"), how="outer")
        .join(_contar(c, c["peso"]).add_suffix("_mfe"), how="outer")
        .fillna(0).astype("int64").reset_index()
    )


def resumo_validacao(comp: pd.DataFrame) -> dict[str, float]:
    """Diferença total relativa à base (%), por leitura e movimento."""
    return {
        f"{m}_{leitura}": 100 * (comp[f"{m}_{leitura}"].sum() / comp[f"{m}_base"].sum() - 1)
        for leitura in ("mov", "mfe") for m in ("adm", "desl")
    }


def validar(consolidado_parquet: Path = DESTINO, base_csv: Path = BASE_FORNECIDA, destino: Path = DESTINO_VALIDACAO) -> dict[str, float]:
    colunas = ["competênciamov", "município", "saldomovimentação"]
    consolidado = pd.read_parquet(consolidado_parquet, columns=colunas + ["tipo_arquivo", "peso"])
    base = pd.read_csv(base_csv, sep=";", usecols=colunas, dtype=str)
    comp = comparar_com_base(consolidado, base)
    comp.to_csv(destino, index=False)
    resumo = resumo_validacao(comp)
    log_etapa("caged24", "diferença × base fornecida (%): " + ", ".join(f"{k} {v:+.3f}" for k, v in resumo.items()))
    return resumo


if __name__ == "__main__":
    import sys

    validar() if "--validar" in sys.argv else consolidar()
