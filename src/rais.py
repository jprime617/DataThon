"""Leitura da RAIS 2025 (vínculos) restrita a Santa Catarina e à CLT (M4.C2).

A RAIS dá o que o CAGED não tem: o **estoque** de vínculos em 31/12/2025, que o
M4 usa como aproximação do estoque médio da janela set/25–ago/26 (rotatividade
descontada, variação relativa) e o **tempo de casa** dos desligados (desligamento
precoce). Este módulo só lê e filtra; o estoque por recorte sai no M4.C3.

Formato do arquivo (conferido no layout oficial e no próprio arquivo de 2025;
ver PLANO_RETA_FINAL, M4 → Estado):

- `RAIS_VINC_PUB_SUL.COMT`, com PR, SC e RS juntos, cerca de 4,3 GB;
- separador **vírgula** (o layout diz `;`, mas está errado para 2025),
  encoding **Latin-1**, decimal `.`;
- alguns códigos vêm entre aspas e com espaço à esquerda (`" 4772500"`), por
  isso tudo é lido como texto e passa por ``strip``.

A leitura é feita em blocos (`chunksize`): o arquivo não cabe na memória e só
cerca de um terço das linhas é de SC.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from src.erros import ErroDeValidacao
from src.logging_pipeline import log_etapa
from src.metricas import COLUNA_CHAVE_MUNICIPAL

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_PADRAO = RAIZ / "data" / "raw" / "rais" / "2025" / "RAIS_VINC_PUB_SUL.COMT"
DESTINO_PADRAO = RAIZ / "data" / "interim" / "rais_sc_2025.parquet"

SEPARADOR = ","
ENCODING = "latin-1"

# Cabeçalho de origem → nome usado no pipeline. Só estas colunas são lidas.
COLUNA_TIPO_VINCULO = "tipo_vinculo"
COLUNA_ATIVO_31DEZ = "ativo_31dez"
COLUNA_MOTIVO_DESLIGAMENTO = "motivo_desligamento"
COLUNA_MES_ADMISSAO = "mes_admissao"
COLUNA_MES_DESLIGAMENTO = "mes_desligamento"
COLUNA_TEMPO_EMPREGO = "tempo_emprego_meses"
COLUNA_ESCOLARIDADE = "escolaridade"
COLUNA_CBO = "cbo"
COLUNA_SUBCLASSE = "subclasse"
COLUNA_REMUNERACAO_MEDIA = "remuneracao_media"

COLUNAS_ORIGEM = {
    "Município - Código": COLUNA_CHAVE_MUNICIPAL,
    "Tipo Vínculo - Código": COLUNA_TIPO_VINCULO,
    "Ind Vínculo Ativo 31/12 - Código": COLUNA_ATIVO_31DEZ,
    "Motivo Desligamento - Código": COLUNA_MOTIVO_DESLIGAMENTO,
    "Mês Admissão - Código": COLUNA_MES_ADMISSAO,
    "Mês Desligamento - Código": COLUNA_MES_DESLIGAMENTO,
    "Tempo Emprego": COLUNA_TEMPO_EMPREGO,
    "Escolaridade Após 2005 - Código": COLUNA_ESCOLARIDADE,
    "CBO 2002 Ocupação - Código": COLUNA_CBO,
    "CNAE 2.0 Subclasse - Codigo": COLUNA_SUBCLASSE,  # sic: sem acento na origem
    "Vl Rem Média Nom": COLUNA_REMUNERACAO_MEDIA,
}

# Tipos de vínculo CLT segundo o layout: 10/15/20/25 (prazo indeterminado) e
# 60/65/70/75 (prazo determinado). Ficam de fora estatutários (30–35), avulso
# (40), temporário (50), aprendiz (55), diretor (80) e contratos 90–97.
TIPOS_VINCULO_CLT = frozenset({10, 15, 20, 25, 60, 65, 70, 75})

# Prefixo IBGE de Santa Catarina na chave de 6 dígitos.
PREFIXO_SC = "42"

_INTEIRAS = {
    COLUNA_TIPO_VINCULO: "int16",
    COLUNA_ATIVO_31DEZ: "int8",
    COLUNA_MOTIVO_DESLIGAMENTO: "int16",
    COLUNA_MES_ADMISSAO: "int8",
    COLUNA_MES_DESLIGAMENTO: "int8",
    COLUNA_ESCOLARIDADE: "int8",
}
_DECIMAIS = (COLUNA_TEMPO_EMPREGO, COLUNA_REMUNERACAO_MEDIA)


def _filtrar_e_tipar(bloco: pd.DataFrame) -> pd.DataFrame:
    """Aplica o filtro SC + CLT a um bloco cru (texto) e converte os tipos."""
    bloco = bloco.rename(columns=COLUNAS_ORIGEM)
    for coluna in bloco.columns:
        bloco[coluna] = bloco[coluna].str.strip()

    municipio = bloco[COLUNA_CHAVE_MUNICIPAL]
    eh_sc = municipio.str.len().eq(6) & municipio.str.startswith(PREFIXO_SC)
    tipo = pd.to_numeric(bloco[COLUNA_TIPO_VINCULO], errors="coerce")
    bloco = bloco[eh_sc & tipo.isin(TIPOS_VINCULO_CLT)].copy()

    for coluna, dtype in _INTEIRAS.items():
        # Ignorado na origem vem como -1 (ou vazio); vira -1 para caber no int.
        bloco[coluna] = (
            pd.to_numeric(bloco[coluna], errors="coerce").fillna(-1).astype(dtype)
        )
    for coluna in _DECIMAIS:
        bloco[coluna] = pd.to_numeric(bloco[coluna], errors="coerce").astype("float32")
    bloco[COLUNA_SUBCLASSE] = bloco[COLUNA_SUBCLASSE].str.zfill(7)
    return bloco


def ler_rais_sc(
    caminho: str | os.PathLike[str] = CAMINHO_PADRAO,
    destino: str | os.PathLike[str] | None = DESTINO_PADRAO,
    *,
    chunksize: int = 500_000,
) -> pd.DataFrame:
    """Lê a RAIS de vínculos, mantém só SC e CLT e grava o parquet intermediário.

    Args:
        caminho: arquivo extraído da RAIS (``.COMT``/``.txt``).
        destino: parquet de saída; ``None`` não grava.
        chunksize: linhas por bloco de leitura.

    Returns:
        Um vínculo por linha, com as colunas de `COLUNAS_ORIGEM` renomeadas e
        `chave_municipal` de 6 dígitos.

    Raises:
        ErroDeValidacao: arquivo ausente ou sem alguma coluna esperada.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ErroDeValidacao(f"Arquivo da RAIS ausente: {str(caminho)!r}")

    cabecalho = pd.read_csv(caminho, sep=SEPARADOR, encoding=ENCODING, nrows=0)
    faltando = sorted(set(COLUNAS_ORIGEM) - set(cabecalho.columns))
    if faltando:
        raise ErroDeValidacao(
            f"RAIS {str(caminho)!r} sem as colunas esperadas: {faltando}"
        )

    blocos = []
    lidas = 0
    leitor = pd.read_csv(
        caminho,
        sep=SEPARADOR,
        encoding=ENCODING,
        dtype=str,
        usecols=list(COLUNAS_ORIGEM),
        chunksize=chunksize,
    )
    for bloco in leitor:
        lidas += len(bloco)
        blocos.append(_filtrar_e_tipar(bloco))

    colunas = list(COLUNAS_ORIGEM.values())
    df = pd.concat(blocos, ignore_index=True)[colunas] if blocos else pd.DataFrame(columns=colunas)

    if destino is not None:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(destino, index=False)
    log_etapa(
        "rais",
        f"{lidas:,} vínculos lidos; {len(df):,} de SC na CLT"
        + (f" → {destino}" if destino is not None else ""),
    )
    return df


if __name__ == "__main__":
    ler_rais_sc()
