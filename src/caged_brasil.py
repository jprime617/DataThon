"""Benchmark SC × Brasil por seção CNAE (ANA-04), a partir dos mesmos `.7z` do CAGED.

Os arquivos baixados por `src.download` são **nacionais**: `src.caged24` só
guarda SC (`uf == 42`). Este módulo relê os 72 `.7z` (MOV + FOR − EXC, a mesma
janela set/24–ago/26) e soma, por abrangência (SC e Brasil) × seção × mês, as
contagens que a saída voluntária precisa. Nada de microdado vai para o disco: o
resultado é uma tabela de poucos KB, `data_processed/caged_brasil_secao.parquet`.

As regras são as do agregado (`src.agregador`): peso +1 para MOV e FOR e −1 para
EXC; desligamento a pedido = tipo 40; descontados = sem 40, 50, 60 e 80. Assim a
linha de SC desta tabela fecha com o agregado do painel, e a do Brasil é
comparável a ela.

A rotatividade por seção do Brasil precisaria do estoque nacional (RAIS de todas
as regiões, vários GB): fica no roadmap.

Uso::

    python -m src.caged_brasil   # grava data_processed/caged_brasil_secao.parquet
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd

from src.agregador import CODIGO_DESLIGAMENTO_A_PEDIDO, CODIGOS_NAO_DESCONTADOS
from src.caged24 import PESO, UF_SC, _comando
from src.download import DESTINO as DIR_7Z, FIM, INICIO, TIPOS, competencias
from src.logging_pipeline import log_etapa

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data_processed" / "caged_brasil_secao.parquet"
COLUNAS_LIDAS = ["competênciamov", "uf", "seção", "saldomovimentação", "tipomovimentação"]
ABRANGENCIA_SC, ABRANGENCIA_BRASIL = "SC", "Brasil"
CHAVE = ["abrangencia", "secao", "mes"]
CONTAGENS = ["admissoes", "desligamentos", "desligamentos_a_pedido", "desligamentos_descontados"]


def contar_bloco(bloco: pd.DataFrame, peso: int, inicio: int = INICIO, fim: int = FIM) -> pd.DataFrame:
    """Um bloco de linhas cruas → contagens por abrangência × seção × mês.

    O Brasil inclui SC (como nas tabelas oficiais). Linhas fora da janela ou com
    movimentação que não é ±1 ficam fora.
    """
    comp = pd.to_numeric(bloco["competênciamov"], errors="coerce")
    mov = pd.to_numeric(bloco["saldomovimentação"], errors="coerce")
    tipo = pd.to_numeric(bloco["tipomovimentação"], errors="coerce")
    ok = comp.between(inicio, fim) & mov.isin([1, -1])
    desl = mov == -1
    base = pd.DataFrame({
        "secao": bloco["seção"].astype(str).str.strip(),
        "mes": comp.astype("Int64").astype(str),
        "admissoes": (mov == 1).astype("int64") * peso,
        "desligamentos": desl.astype("int64") * peso,
        "desligamentos_a_pedido": (desl & (tipo == CODIGO_DESLIGAMENTO_A_PEDIDO)).astype("int64") * peso,
        "desligamentos_descontados": (desl & ~tipo.isin(CODIGOS_NAO_DESCONTADOS)).astype("int64") * peso,
    })[ok]
    sc = bloco.loc[ok, "uf"].astype(str).str.strip() == UF_SC
    partes = [base.assign(abrangencia=ABRANGENCIA_BRASIL), base[sc.values].assign(abrangencia=ABRANGENCIA_SC)]
    return pd.concat(partes).groupby(CHAVE, as_index=False)[CONTAGENS].sum()


def ler_arquivo(arquivo: Path, tipo: str, inicio: int = INICIO, fim: int = FIM,
                chunksize: int = 1_000_000) -> pd.DataFrame:
    """Um `.7z` nacional → contagens (só as 5 colunas necessárias são lidas)."""
    proc = subprocess.Popen(_comando(arquivo), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    partes = []
    try:
        for bloco in pd.read_csv(proc.stdout, sep=";", dtype=str, encoding="utf-8", usecols=COLUNAS_LIDAS,
                                 chunksize=chunksize):
            partes.append(contar_bloco(bloco, PESO[tipo], inicio, fim))
    finally:
        proc.stdout.close()
        if proc.wait() != 0:
            raise RuntimeError(f"falha ao descompactar {arquivo}")
    return pd.concat(partes).groupby(CHAVE, as_index=False)[CONTAGENS].sum()


def rotular_secoes(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta `secao_industrial` com o rótulo do dicionário (o mesmo do agregado)."""
    from src.mapeamentos import SECAO_CNAE

    resultado = df.copy()
    resultado["secao_industrial"] = resultado["secao"].map(SECAO_CNAE).fillna(resultado["secao"])
    return resultado


def consolidar(diretorio: Path = DIR_7Z, destino: Path | None = DESTINO,
               inicio: int = INICIO, fim: int = FIM) -> pd.DataFrame:
    partes = []
    for c in competencias(inicio, fim):
        for tipo in TIPOS:
            arquivo = diretorio / f"CAGED{tipo}{c}.7z"
            if not arquivo.exists():
                raise FileNotFoundError(f"{arquivo} ausente: rode `python -m src.download`")
            partes.append(ler_arquivo(arquivo, tipo, inicio, fim))
            log_etapa("caged_brasil", f"{arquivo.name} lido")
    df = rotular_secoes(pd.concat(partes).groupby(CHAVE, as_index=False)[CONTAGENS].sum())
    if destino is not None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(destino, index=False)
    tot = df.groupby("abrangencia")[["admissoes", "desligamentos"]].sum().to_dict("index")
    log_etapa("caged_brasil", f"{len(df)} linhas; totais {tot}")
    return df


if __name__ == "__main__":
    consolidar()
