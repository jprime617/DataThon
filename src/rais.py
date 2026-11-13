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

from src import mapeamentos
from src.agregador import NIVEL_NAO_INFORMADO
from src.cbo_ia import CAMINHO_CSV_PADRAO, COLUNA_CBO as COLUNA_CBO_CAGED, COLUNA_MACROFAMILIA, COLUNA_NIVEL, aplicar_mapeamento
from src.erros import ErroDeValidacao
from src.logging_pipeline import log_etapa
from src.metricas import COLUNA_CHAVE_MUNICIPAL

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_PADRAO = RAIZ / "data" / "raw" / "rais" / "2025" / "RAIS_VINC_PUB_SUL.COMT"
DESTINO_PADRAO = RAIZ / "data" / "interim" / "rais_sc_2025.parquet"
ESTOQUE_PADRAO = RAIZ / "data_processed" / "rais_estoque.parquet"

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


# Divisão CNAE (2 primeiros dígitos da subclasse) → letra da seção, CNAE 2.0.
# A RAIS não traz a letra; conferido contra seção × subclasse do CAGED.
_SECAO_POR_DIVISAO = {
    d: letra
    for letra, (ini, fim) in {
        "A": (1, 3), "B": (5, 9), "C": (10, 33), "D": (35, 35), "E": (36, 39),
        "F": (41, 43), "G": (45, 47), "H": (49, 53), "I": (55, 56), "J": (58, 63),
        "K": (64, 66), "L": (68, 68), "M": (69, 75), "N": (77, 82), "O": (84, 84),
        "P": (85, 85), "Q": (86, 88), "R": (90, 93), "S": (94, 96), "T": (97, 97),
        "U": (99, 99),
    }.items()
    for d in range(ini, fim + 1)
}

# Motivos de desligamento 30–34 são transferências, não desligamentos de
# verdade (RAIS ≠ CAGED; ver PLANO_RETA_FINAL, M4 → Estado).
MOTIVOS_TRANSFERENCIA = range(30, 35)
ESCOLARIDADE_MEDIO_COMPLETO = 7  # RAIS 1–11; −1 = ignorado
MESES_PRECOCE = 12

# Mesmas dimensões do agregado do CAGED, sem `mes`.
CHAVES_ESTOQUE = ["municipio", "secao_industrial", "setor", "macrofamilia_cbo", "nivel_qualificacao"]
COLUNAS_ESTOQUE = [
    "estoque_31dez",
    "estoque_escolaridade_informada",
    "estoque_medio_ou_mais",
    "desligados_rais",
    "desligados_precoce",
]


def estoque_rais(
    vinculos: pd.DataFrame,
    destino: str | os.PathLike[str] | None = ESTOQUE_PADRAO,
    *,
    caminho_cbo: str = CAMINHO_CSV_PADRAO,
    caminho_referencia: str | os.PathLike[str] | None = None,
    caminho_overrides: str | os.PathLike[str] | None = None,
) -> pd.DataFrame:
    """Estoque de 31/12 e desligados da RAIS por recorte do agregado (M4.C3).

    Colunas aditivas por (município × seção × setor × macrofamília × nível):
    `estoque_31dez`, `estoque_escolaridade_informada` (denominador da
    escolaridade: o estoque sem os ignorados), `estoque_medio_ou_mais`,
    `desligados_rais` (sem as transferências 30–34) e `desligados_precoce`
    (desligados com menos de 12 meses de casa).
    """
    divisao = pd.to_numeric(vinculos[COLUNA_SUBCLASSE], errors="coerce") // 100_000
    letra = divisao.map(_SECAO_POR_DIVISAO).fillna("Z")
    secao = letra.map(lambda l: mapeamentos.SECAO_CNAE.get(l, l))
    setor = divisao.map(mapeamentos.SETOR_POR_DIVISAO_TRANSFORMACAO).where(letra == "C")

    # A mesma classificação final do CAGED (desempate e overrides), para o estoque casar com o agregado.
    cbos = aplicar_mapeamento(vinculos[[COLUNA_CBO]].rename(columns={COLUNA_CBO: COLUNA_CBO_CAGED}), caminho_cbo,
                              caminho_referencia=caminho_referencia, caminho_overrides=caminho_overrides)

    ativo = vinculos[COLUNA_ATIVO_31DEZ] == 1
    esc = vinculos[COLUNA_ESCOLARIDADE]
    motivo = vinculos[COLUNA_MOTIVO_DESLIGAMENTO]
    desligado = (motivo > 0) & ~motivo.isin(MOTIVOS_TRANSFERENCIA)

    base = pd.DataFrame({
        "municipio": vinculos[COLUNA_CHAVE_MUNICIPAL].values,
        "secao_industrial": secao.values,
        "setor": setor.fillna(secao).values,
        "macrofamilia_cbo": cbos[COLUNA_MACROFAMILIA].values,
        "nivel_qualificacao": cbos[COLUNA_NIVEL].fillna(NIVEL_NAO_INFORMADO).values,
        "estoque_31dez": ativo.values,
        "estoque_escolaridade_informada": (ativo & (esc > 0)).values,
        "estoque_medio_ou_mais": (ativo & (esc >= ESCOLARIDADE_MEDIO_COMPLETO)).values,
        "desligados_rais": desligado.values,
        "desligados_precoce": (desligado & (vinculos[COLUNA_TEMPO_EMPREGO] < MESES_PRECOCE)).values,
    })
    estoque = (
        base.groupby(CHAVES_ESTOQUE, dropna=False)[COLUNAS_ESTOQUE].sum().astype("int64").reset_index()
    )

    sem_macro = estoque.loc[estoque["macrofamilia_cbo"].isna(), "estoque_31dez"].sum()
    pct = sem_macro / max(estoque["estoque_31dez"].sum(), 1)
    if destino is not None:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        estoque.to_parquet(destino, index=False)
    log_etapa(
        "rais",
        f"estoque 31/12: {estoque['estoque_31dez'].sum():,}; desligados: "
        f"{estoque['desligados_rais'].sum():,}; {pct:.2%} do estoque sem macrofamília"
        + (" (acima de 1%: acionar M2.C5)" if pct > 0.01 else ""),
    )
    return estoque


if __name__ == "__main__":
    import sys

    if "--estoque" in sys.argv:
        from src.cbo_ia import NOME_CSV_REFERENCIA

        estoque_rais(pd.read_parquet(DESTINO_PADRAO),
                     caminho_referencia=Path(CAMINHO_CSV_PADRAO).with_name(NOME_CSV_REFERENCIA))
    else:
        ler_rais_sc()
