"""Núcleo compartilhado do dashboard v2: dados, métricas, formatação e tema.

Tudo aqui é **puro** (sem Streamlit) e testável, exceto as poucas funções
``*_streamlit`` no fim do módulo, que importam o Streamlit de forma tardia.
As páginas (``dashboard/paginas/*.py``) só orquestram: filtram, chamam o motor
de métricas, constroem figuras e escrevem texto calculado a partir dos dados.

Princípio central — **somar antes de dividir**: o agregado traz contagens e
somas por célula (``admissoes``, ``soma_salario_admissao``…). Qualquer recorte é
reagregado somando essas colunas e só então as razões são derivadas
(`agregar_metricas`). Promediar razões de células faria uma célula com uma
admissão pesar o mesmo que uma com cinco mil.
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_RAIZ_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_PROJETO))

import pandas as pd

from src.agregador import (
    COLUNA_ADMISSOES,
    COLUNA_DESLIGAMENTOS,
    COLUNA_DESLIGAMENTOS_A_PEDIDO,
    COLUNA_ESCOPO_INDUSTRIAL,
    COLUNA_FAIXA_ESCOLARIDADE,
    COLUNA_IDHM_2010,
    COLUNA_MACROFAMILIA_CBO,
    COLUNA_MEDIANA_SALARIO_ADMISSAO,
    COLUNA_MEDIANA_SALARIO_DESLIGAMENTO,
    COLUNA_MES,
    COLUNA_MICRORREGIAO,
    COLUNA_MUNICIPIO,
    COLUNA_NIVEL_QUALIFICACAO,
    COLUNA_NOME_MUNICIPIO,
    COLUNA_PIB_PER_CAPITA_2023,
    COLUNA_POPULACAO_2026,
    COLUNA_REGIAO,
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SECAO_INDUSTRIAL,
    COLUNA_SETOR,
    COLUNAS_ADITIVAS,
)
from src.logging_pipeline import log_etapa, obter_logger
from src.mapeamentos import NAO_CLASSIFICADO

_ETAPA = "dashboard"

# ---------------------------------------------------------------------------
# Carregamento (Blob primeiro, cópia local como fallback — R9)
# ---------------------------------------------------------------------------

_DIR_DADOS = _RAIZ_PROJETO / "data_processed"
_CAMINHO_LOCAL_PADRAO = _DIR_DADOS / "caged_agregado.parquet"
CAMINHO_GEOJSON = _RAIZ_PROJETO / "dashboard" / "geo" / "sc_municipios.geojson"
CAMINHO_CBO = _DIR_DADOS / "cbo_macrofamilias.csv"
CAMINHO_DIVERGENCIAS = _DIR_DADOS / "cbo_divergencias.csv"
CAMINHO_PROMPT = _DIR_DADOS / "cbo_macrofamilias.csv.prompt.txt"

VAR_CREDENCIAL_AZURE = "AZURE_STORAGE_CONNECTION_STRING"
VAR_CONTAINER_AZURE = "AZURE_BLOB_CONTAINER"
CONTAINER_PADRAO = "caged-agregado"
NOME_BLOB_AGREGADO = "caged_agregado.parquet"
NOME_BLOB_PERFIL = "caged_perfil.parquet"
NOME_BLOB_METADADOS = "metadados.json"

# Colunas que o painel v2 exige no agregado. Uma cópia do Blob gerada pelo
# pipeline antigo não as tem: nesse caso o painel usa a cópia local e avisa.
COLUNAS_V2 = [
    COLUNA_SETOR,
    COLUNA_NIVEL_QUALIFICACAO,
    COLUNA_MICRORREGIAO,
    COLUNA_ESCOPO_INDUSTRIAL,
    COLUNA_NOME_MUNICIPIO,
    *COLUNAS_ADITIVAS,
]

TTL_CACHE_DADOS = 600

CarregadorBlob = Callable[[str], pd.DataFrame]


def container_agregados(
    env: "os._Environ[str] | dict[str, str] | None" = None,
) -> str:
    """Nome do container das tabelas agregadas, de `AZURE_BLOB_CONTAINER`."""
    ambiente = os.environ if env is None else env
    return (ambiente.get(VAR_CONTAINER_AZURE) or "").strip() or CONTAINER_PADRAO


@dataclass(frozen=True)
class ResultadoCarregamento:
    """Resultado da resolução da origem das tabelas agregadas (R7.7, R7.8, R9)."""

    df: pd.DataFrame | None
    disponivel: bool
    origem: str | None = None
    motivo: str | None = None


def _baixar_blob(connection_string: str, nome: str) -> bytes:
    """Baixa um blob do container configurado (SDK importado tardiamente)."""
    from azure.storage.blob import BlobServiceClient

    servico = BlobServiceClient.from_connection_string(connection_string)
    cliente = servico.get_blob_client(container=container_agregados(), blob=nome)
    return cliente.download_blob().readall()


def _carregar_blob_padrao(connection_string: str) -> pd.DataFrame:
    """Lê a tabela agregada do Blob_Storage (R9.2)."""
    return pd.read_parquet(io.BytesIO(_baixar_blob(connection_string, NOME_BLOB_AGREGADO)))


def carregar_dados(
    *,
    blob_loader: CarregadorBlob | None = None,
    caminho_local: str | Path | None = None,
    env: "os._Environ[str] | dict[str, str] | None" = None,
) -> ResultadoCarregamento:
    """Resolve a origem da tabela agregada: Blob → local → indisponível (R9).

    Nunca levanta: com as duas origens indisponíveis, devolve
    ``disponivel=False`` e um `motivo` legível (R7.8).
    """
    logger = obter_logger()
    ambiente = os.environ if env is None else env
    caminho = Path(caminho_local) if caminho_local is not None else _CAMINHO_LOCAL_PADRAO
    carregador = blob_loader or _carregar_blob_padrao
    motivos: list[str] = []

    credencial = (ambiente.get(VAR_CREDENCIAL_AZURE) or "").strip()
    if credencial:
        try:
            df_blob = carregador(credencial)
            log_etapa(_ETAPA, f"agregado carregado do Blob ({len(df_blob)} linhas).", logger=logger)
            return ResultadoCarregamento(df=df_blob, disponivel=True, origem="blob")
        except Exception as exc:  # noqa: BLE001 — qualquer falha de Blob → fallback.
            motivos.append(f"Blob_Storage indisponível ({exc}).")
            logger.warning("[%s] Blob falhou; tentando a cópia local: %s", _ETAPA, exc)
    else:
        motivos.append(
            f"Blob_Storage indisponível (credencial {VAR_CREDENCIAL_AZURE!r} ausente ou vazia)."
        )

    try:
        df_local = pd.read_parquet(caminho)
        log_etapa(_ETAPA, f"agregado carregado de {str(caminho)!r} ({len(df_local)} linhas).", logger=logger)
        return ResultadoCarregamento(df=df_local, disponivel=True, origem="local")
    except Exception as exc:  # noqa: BLE001
        motivos.append(f"cópia local indisponível em {str(caminho)!r} ({exc}).")

    motivo = "Dados agregados indisponíveis. " + " ".join(motivos)
    logger.error("[%s] %s", _ETAPA, motivo)
    return ResultadoCarregamento(df=None, disponivel=False, origem=None, motivo=motivo)


@dataclass(frozen=True)
class Artefatos:
    """Tudo o que o painel lê, já validado, com a origem e avisos visíveis."""

    agregado: pd.DataFrame | None
    perfil: pd.DataFrame | None
    metadados: dict
    origem: str | None
    avisos: tuple[str, ...] = ()
    motivo: str | None = None

    @property
    def disponivel(self) -> bool:
        return self.agregado is not None


# Colunas legadas (R6) que o painel v2 não lê: ficam no arquivo para o app
# antigo, mas não entram na memória do servidor.
_COLUNAS_LEGADAS = {
    "saldo_liquido", "saldo_por_10k", "turnover", "indice_aquecimento",
    "salario_medio_admissao", "salario_medio_desligamento", "escolaridade_media",
}


def ler_parquet_enxuto(fonte) -> pd.DataFrame:
    """Lê um Parquet com textos já como categorias e sem as colunas legadas.

    Ler direto em dicionário evita materializar milhões de objetos `str` só
    para convertê-los em seguida — o que, no B1, custava centenas de MB.
    """
    import pyarrow.parquet as pq

    esquema = pq.read_schema(fonte)
    if hasattr(fonte, "seek"):
        fonte.seek(0)
    colunas = [n for n in esquema.names if n not in _COLUNAS_LEGADAS]
    textos = [n for n in colunas if str(esquema.field(n).type) in ("string", "large_string")]
    return pq.read_table(fonte, columns=colunas, read_dictionary=textos).to_pandas()


def schema_v2_ok(df: pd.DataFrame | None) -> bool:
    """O agregado tem todas as colunas que o painel v2 exige?"""
    return df is not None and set(COLUNAS_V2) <= set(df.columns)


def carregar_artefatos(
    *,
    baixar: Callable[[str, str], bytes] | None = None,
    dir_local: str | Path | None = None,
    env: "os._Environ[str] | dict[str, str] | None" = None,
) -> Artefatos:
    """Carrega agregado, perfil e metadados, validando o schema (Blob → local).

    Se o agregado do Blob vier no schema antigo (sem as colunas v2), o painel
    usa o conjunto local inteiro e diz isso na tela — nunca mistura origens.
    """
    baixar = baixar or _baixar_blob
    pasta = Path(dir_local) if dir_local is not None else _DIR_DADOS
    ambiente = os.environ if env is None else env
    avisos: list[str] = []

    def _ler_local() -> tuple[pd.DataFrame | None, pd.DataFrame | None, dict]:
        agregado = perfil = None
        meta: dict = {}
        try:
            agregado = ler_parquet_enxuto(pasta / NOME_BLOB_AGREGADO)
        except Exception as exc:  # noqa: BLE001
            avisos.append(f"Cópia local do agregado ilegível ({exc}).")
        try:
            perfil = ler_parquet_enxuto(pasta / NOME_BLOB_PERFIL)
        except Exception:  # noqa: BLE001
            avisos.append("Perfil de causa raiz indisponível na cópia local.")
        try:
            meta = json.loads((pasta / NOME_BLOB_METADADOS).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            avisos.append("Metadados indisponíveis na cópia local.")
        return agregado, perfil, meta

    credencial = (ambiente.get(VAR_CREDENCIAL_AZURE) or "").strip()
    if credencial:
        try:
            agregado = ler_parquet_enxuto(io.BytesIO(baixar(credencial, NOME_BLOB_AGREGADO)))
            if not schema_v2_ok(agregado):
                raise ValueError("a cópia do Blob está no schema antigo (sem as colunas v2)")
            perfil = ler_parquet_enxuto(io.BytesIO(baixar(credencial, NOME_BLOB_PERFIL)))
            meta = json.loads(baixar(credencial, NOME_BLOB_METADADOS).decode("utf-8"))
            return Artefatos(preparar_tipos(agregado), perfil, meta, "blob", tuple(avisos))
        except Exception as exc:  # noqa: BLE001
            avisos.append(f"Azure Blob não usado: {exc}. Exibindo a cópia local.")
    else:
        avisos.append("Sem credencial do Azure Blob: exibindo a cópia local.")

    agregado, perfil, meta = _ler_local()
    if agregado is not None and not schema_v2_ok(agregado):
        return Artefatos(None, None, {}, None, tuple(avisos),
                         "A cópia local do agregado está no schema antigo; rode o pipeline.")
    if agregado is None:
        return Artefatos(None, None, {}, None, tuple(avisos),
                         "Dados agregados indisponíveis no Blob e na cópia local.")
    return Artefatos(preparar_tipos(agregado), perfil, meta, "local", tuple(avisos))


def preparar_tipos(df: pd.DataFrame) -> pd.DataFrame:
    """Dimensões textuais como categorias: filtros e groupbys bem mais rápidos."""
    resultado = df
    for coluna in (
        COLUNA_REGIAO, COLUNA_MICRORREGIAO, COLUNA_MUNICIPIO, COLUNA_NOME_MUNICIPIO,
        COLUNA_SECAO_INDUSTRIAL, COLUNA_SETOR, COLUNA_MACROFAMILIA_CBO,
        COLUNA_NIVEL_QUALIFICACAO, COLUNA_MES,
    ):
        if coluna in resultado.columns:
            serie = resultado[coluna]
            if not isinstance(serie.dtype, pd.CategoricalDtype):
                serie = serie.astype(str).astype("category")
            # Categorias em ordem alfabética/cronológica: o dicionário do Parquet
            # vem na ordem do arquivo, e ordenar por ele embaralharia os meses.
            resultado[coluna] = serie.cat.reorder_categories(sorted(serie.cat.categories, key=str))
    return resultado


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

ESCOPO_INDUSTRIA = "Indústria (B–F)"
ESCOPO_ECONOMIA = "Toda a economia"
NIVEL_MESO = "Mesorregião"
NIVEL_MICRO = "Microrregião"
NIVEL_MUNICIPIO = "Município"
COLUNA_POR_NIVEL_TERRITORIAL = {
    NIVEL_MESO: COLUNA_REGIAO,
    NIVEL_MICRO: COLUNA_MICRORREGIAO,
    NIVEL_MUNICIPIO: COLUNA_NOME_MUNICIPIO,
}


@dataclass(frozen=True)
class Filtros:
    """Estado dos filtros globais (persistido em `st.session_state`)."""

    escopo: str = ESCOPO_INDUSTRIA
    meses: tuple[str, str] | None = None
    nivel_territorial: str = NIVEL_MESO
    territorios: tuple[str, ...] = ()
    setores: tuple[str, ...] = ()
    macrofamilias: tuple[str, ...] = ()
    niveis: tuple[str, ...] = ()

    def descricao(self) -> str:
        """Uma linha compacta com os filtros ativos."""
        partes = [self.escopo]
        if self.meses:
            partes.append(f"{rotulo_mes(self.meses[0])}–{rotulo_mes(self.meses[1])}")
        for nome, valores in (
            (self.nivel_territorial, self.territorios),
            ("Setor", self.setores),
            ("Macrofamília", self.macrofamilias),
            ("Nível", self.niveis),
        ):
            if valores:
                lista = ", ".join(valores[:3]) + (f" +{len(valores) - 3}" if len(valores) > 3 else "")
                partes.append(f"{nome}: {lista}")
        return " · ".join(partes)


def _mascara_dimensao(df: pd.DataFrame, coluna: str, selecao) -> pd.Series:
    """Máscara de um filtro opcional: ``None``/vazio = sem restrição."""
    if selecao is None or coluna not in df.columns:
        return pd.Series(True, index=df.index)
    if isinstance(selecao, (list, tuple, set, frozenset, pd.Series)):
        valores = list(selecao)
        if not valores:
            return pd.Series(True, index=df.index)
        return df[coluna].isin(valores)
    return df[coluna] == selecao


def aplicar_filtros(
    df: pd.DataFrame,
    periodo=None,
    regiao=None,
    secao=None,
    macrofamilia=None,
    **outras,
) -> pd.DataFrame:
    """Filtra a tabela pelas dimensões dadas, em conjunção (R7.5).

    ``periodo``/``regiao``/``secao``/``macrofamilia`` mantêm o contrato do
    painel original; ``outras`` aceita ``coluna=selecao`` para as dimensões v2.
    Seleção ``None`` ou vazia não restringe. Devolve uma cópia (talvez vazia).
    """
    mascara = pd.Series(True, index=df.index)
    for coluna, selecao in (
        (COLUNA_MES, periodo),
        (COLUNA_REGIAO, regiao),
        (COLUNA_SECAO_INDUSTRIAL, secao),
        (COLUNA_MACROFAMILIA_CBO, macrofamilia),
        *outras.items(),
    ):
        mascara &= _mascara_dimensao(df, coluna, selecao)
    return df[mascara].copy()


def filtrar(df: pd.DataFrame, filtros: Filtros, *, ignorar: tuple[str, ...] = ()) -> pd.DataFrame:
    """Aplica os filtros globais; ``ignorar`` pula dimensões (ex.: território)."""
    if df is None or df.empty:
        return df
    selecoes: dict[str, object] = {}
    if filtros.escopo == ESCOPO_INDUSTRIA and COLUNA_ESCOPO_INDUSTRIAL in df.columns:
        selecoes[COLUNA_ESCOPO_INDUSTRIAL] = True
    if filtros.meses and "periodo" not in ignorar and COLUNA_MES in df.columns:
        meses = df[COLUNA_MES].astype(str)
        df = df[(meses >= filtros.meses[0]) & (meses <= filtros.meses[1])]
    if "territorio" not in ignorar:
        selecoes[COLUNA_POR_NIVEL_TERRITORIAL[filtros.nivel_territorial]] = filtros.territorios
    selecoes[COLUNA_SETOR] = filtros.setores
    selecoes[COLUNA_MACROFAMILIA_CBO] = filtros.macrofamilias
    selecoes[COLUNA_NIVEL_QUALIFICACAO] = filtros.niveis
    return aplicar_filtros(df, **selecoes)


# ---------------------------------------------------------------------------
# Motor de métricas: somar as colunas aditivas, depois derivar as razões
# ---------------------------------------------------------------------------

MIN_MOVIMENTACOES = 100
MIN_SALARIOS = 30
LIMIAR_COMPRESSAO = 0.95

M_MOV = "movimentacoes"
M_SALDO = "saldo"
M_SALDO_10K = "saldo_10k"
M_SAIDA_VOL = "saida_voluntaria"
M_SAL_ADM = "salario_admissao"
M_SAL_DESL = "salario_desligamento"
M_GAP_SAL = "gap_salarial"
M_ESC_ADM = "escolaridade_admissao"
M_ESC_DESL = "escolaridade_desligamento"
M_GAP_ESC = "gap_escolaridade"
M_SALDO_REL = "saldo_relativo"
M_POP = "populacao"
M_AMOSTRA_OK = "amostra_ok"
M_SALARIO_OK = "salario_ok"


@dataclass(frozen=True)
class Definicao:
    """Rótulo, fórmula (tooltip) e formato de exibição de uma métrica."""

    rotulo: str
    formula: str
    formato: str  # "int" | "pct" | "razao" | "brl" | "num1" | "pp"


DEFINICOES: dict[str, Definicao] = {
    M_MOV: Definicao("Movimentações", "admissões + desligamentos", "int"),
    M_SALDO: Definicao("Saldo", "admissões − desligamentos", "int"),
    M_SALDO_10K: Definicao(
        "Saldo por 10 mil hab.",
        "saldo ÷ população 2026 dos municípios distintos da seleção × 10.000",
        "num1",
    ),
    M_SAIDA_VOL: Definicao(
        "Saída voluntária", "desligamentos a pedido (tipo 40) ÷ desligamentos", "pct"
    ),
    M_GAP_SAL: Definicao(
        "Salário de quem entra vs quem saiu",
        "quanto o salário médio de quem é contratado fica abaixo (ou acima) do de quem saiu. "
        "Cálculo: salário médio de admissão ÷ salário médio de desligamento "
        f"(< {str(LIMIAR_COMPRESSAO).replace('.', ',')} = compressão). "
        f"Exige ≥ {MIN_SALARIOS} salários em cada lado. Salário válido: > 0 e ≤ 20× a "
        "mediana estadual (exclui zeros e valores de rescisão/digitação).",
        "gap",
    ),
    M_GAP_ESC: Definicao(
        "Escolaridade de quem entra vs quem saiu",
        "escolaridade média dos admitidos − dos desligados (escala ordinal 1–11; "
        "< 0 = contratando menos escolarizados)",
        "num2",
    ),
    M_SALDO_REL: Definicao("Saldo relativo", "saldo ÷ movimentações", "pct"),
    M_SAL_ADM: Definicao("Salário médio de admissão", "soma dos salários ÷ admissões com salário", "brl"),
    M_SAL_DESL: Definicao("Salário médio de desligamento", "soma dos salários ÷ desligamentos com salário", "brl"),
    M_ESC_ADM: Definicao("Escolaridade média de quem entra",
                         "nível ordinal médio dos admitidos (1 = analfabeto … 11 = doutorado)", "num2"),
    COLUNA_IDHM_2010: Definicao("IDHM 2010", "Índice de Desenvolvimento Humano Municipal (PNUD, 2010)", "num2"),
    COLUNA_PIB_PER_CAPITA_2023: Definicao("PIB per capita 2023", "PIB municipal ÷ população (IBGE, 2023)", "brl"),
}


def _divisao(numerador: pd.Series, denominador: pd.Series) -> pd.Series:
    """Divisão elemento a elemento com 0 no denominador → NaN."""
    den = denominador.astype("float64")
    return numerador.astype("float64") / den.where(den != 0)


def agregar_metricas(df: pd.DataFrame, por: list[str] | None = None) -> pd.DataFrame:
    """Reagrega o recorte e deriva todas as métricas (soma antes de dividir).

    Args:
        df: subconjunto do agregado com as colunas aditivas.
        por: dimensões do resultado; ``None``/``[]`` = uma linha com o total.

    Returns:
        Uma linha por grupo com contagens, razões e as flags de amostra.
    """
    por = list(por or [])
    base = df
    if not por:
        base = df.assign(_todos=0)
    chave = por or ["_todos"]

    if base.empty:
        if por:
            somas = pd.DataFrame({c: pd.Series(dtype="object") for c in por})
            for c in COLUNAS_ADITIVAS:
                somas[c] = pd.Series(dtype="float64")
        else:
            somas = pd.DataFrame([{c: 0 for c in COLUNAS_ADITIVAS}])
        return _derivar(somas, [float("nan")] * len(somas))

    agrupado = base.groupby(chave, observed=True, dropna=False)
    somas = agrupado[COLUNAS_ADITIVAS].sum()

    # População: soma dos municípios DISTINTOS do grupo (nunca por linha).
    if {COLUNA_POPULACAO_2026, COLUNA_MUNICIPIO} <= set(base.columns):
        distintos = base.drop_duplicates([*chave, COLUNA_MUNICIPIO])
        populacao = (
            distintos.groupby(chave, observed=True, dropna=False)[COLUNA_POPULACAO_2026]
            .sum(min_count=1)
            .reindex(somas.index)
        )
    else:
        populacao = pd.Series(float("nan"), index=somas.index)

    somas = somas.reset_index()
    if not por:
        somas = somas.drop(columns="_todos")
    return _derivar(somas, populacao.to_numpy())


def _derivar(somas: pd.DataFrame, populacao) -> pd.DataFrame:
    """Deriva as razões a partir das somas de cada grupo."""
    r = somas.copy()
    adm = r[COLUNA_ADMISSOES].astype("float64")
    desl = r[COLUNA_DESLIGAMENTOS].astype("float64")
    r[M_MOV] = adm + desl
    r[M_SALDO] = adm - desl
    r[M_POP] = pd.Series(populacao, index=r.index, dtype="float64")
    r[M_SALDO_10K] = _divisao(r[M_SALDO], r[M_POP]) * 10_000
    r[M_SAIDA_VOL] = _divisao(r[COLUNA_DESLIGAMENTOS_A_PEDIDO], desl)
    r[M_SAL_ADM] = _divisao(r["soma_salario_admissao"], r["n_salario_admissao"])
    r[M_SAL_DESL] = _divisao(r["soma_salario_desligamento"], r["n_salario_desligamento"])
    r[M_SALARIO_OK] = (r["n_salario_admissao"].astype("float64") >= MIN_SALARIOS) & (
        r["n_salario_desligamento"].astype("float64") >= MIN_SALARIOS
    )
    r[M_GAP_SAL] = _divisao(r[M_SAL_ADM], r[M_SAL_DESL]).where(r[M_SALARIO_OK])
    r[M_ESC_ADM] = _divisao(r["soma_escolaridade_admissao"], r["n_escolaridade_admissao"])
    r[M_ESC_DESL] = _divisao(r["soma_escolaridade_desligamento"], r["n_escolaridade_desligamento"])
    r[M_GAP_ESC] = r[M_ESC_ADM] - r[M_ESC_DESL]
    r[M_SALDO_REL] = _divisao(r[M_SALDO], r[M_MOV])
    r[M_AMOSTRA_OK] = r[M_MOV] >= MIN_MOVIMENTACOES
    return r


def total(df: pd.DataFrame) -> pd.Series:
    """Métricas do recorte inteiro como uma Series (uma linha)."""
    return agregar_metricas(df, None).iloc[0]


def calcular_kpis(df: pd.DataFrame) -> list[tuple[str, float]]:
    """KPIs do painel como pares ``(rótulo, valor)`` (R7.1, R7.6).

    Com o filtro vazio, contagens valem 0 e razões ficam ``NaN`` (exibidas como
    "—"), em vez de inventar um zero que pareceria um resultado.
    """
    t = total(df)
    return [(DEFINICOES[m].rotulo, float(t[m])) for m in KPIS_PADRAO]


# Os 4 indicadores principais (M3.C3); o resto fica em "Aprofundar".
KPIS_PADRAO = [M_SALDO, M_SALDO_10K, M_SAIDA_VOL, M_GAP_SAL]


# ---------------------------------------------------------------------------
# Diagnóstico: z-scores, matriz Dinamismo × Tensão e causas
# ---------------------------------------------------------------------------

Q_SAUDAVEL = "Expansão saudável"
Q_PRESSAO = "Expansão sob pressão"
Q_ESTAGNACAO = "Estagnação"
Q_APAGAO = "Apagão (rotatividade crônica)"

# Tensão = só sintomas. A compressão salarial é causa (ver `causas`), não sintoma;
# rotatividade descontada e desligamento precoce entram com a RAIS (M4).
PESOS_TENSAO_PADRAO = {M_SAIDA_VOL: 1.0}
# A aceleração semestral media calendário; volta por blocos de 12 meses (M5.C6).
PESOS_DINAMISMO_PADRAO = {M_SALDO_REL: 1.0}

ROTULO_COMPONENTE = {
    M_SAIDA_VOL: "saída voluntária alta",
    M_SALDO_REL: "saldo relativo",
}


def zscore(serie: pd.Series) -> pd.Series:
    """z-score populacional; série constante ou com < 2 valores → 0."""
    s = serie.astype("float64")
    validos = s.dropna()
    if len(validos) < 2:
        return s * 0.0
    desvio = validos.std(ddof=0)
    if not desvio or math.isnan(desvio):
        return s.where(s.isna(), 0.0)
    return (s - validos.mean()) / desvio


def _media_ponderada(componentes: pd.DataFrame, pesos: dict[str, float]) -> pd.Series:
    """Média ponderada linha a linha, ignorando componentes ausentes."""
    numerador = pd.Series(0.0, index=componentes.index)
    denominador = pd.Series(0.0, index=componentes.index)
    for nome, peso in pesos.items():
        valor = componentes[nome]
        presente = valor.notna()
        numerador += valor.fillna(0.0) * peso
        denominador += presente * peso
    return numerador / denominador.where(denominador > 0)


def quadrante(dinamismo: float, tensao: float) -> str:
    """Quadrante da matriz (PLANEJAMENTO §7.2); zero conta como "alto"."""
    if dinamismo >= 0:
        return Q_PRESSAO if tensao >= 0 else Q_SAUDAVEL
    return Q_APAGAO if tensao >= 0 else Q_ESTAGNACAO


def matriz_diagnostico(
    df: pd.DataFrame,
    por: list[str],
    *,
    pesos_tensao: dict[str, float] | None = None,
    pesos_dinamismo: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Unidades com amostra suficiente, com Dinamismo, Tensão, quadrante e motor.

    Os z-scores são calculados **entre as unidades elegíveis** (≥ 100
    movimentações); unidades abaixo disso ficam fora — não há como comparar uma
    taxa de 3 movimentações com uma de 3 mil.
    """
    pesos_tensao = pesos_tensao or PESOS_TENSAO_PADRAO
    pesos_dinamismo = pesos_dinamismo or PESOS_DINAMISMO_PADRAO
    m = agregar_metricas(df, por)
    m = m[m[M_AMOSTRA_OK]].copy()
    if m.empty:
        for c in ("dinamismo", "tensao", "quadrante", "motor"):
            m[c] = pd.Series(dtype="object")
        return m
    comp = pd.DataFrame(
        {
            M_SAIDA_VOL: zscore(m[M_SAIDA_VOL]),
            M_SALDO_REL: zscore(m[M_SALDO_REL]),
        },
        index=m.index,
    )
    m["tensao"] = _media_ponderada(comp, pesos_tensao)
    m["dinamismo"] = _media_ponderada(comp, pesos_dinamismo)
    m["quadrante"] = [quadrante(d, t) for d, t in zip(m["dinamismo"].fillna(0), m["tensao"].fillna(0))]
    componentes_tensao = comp[list(pesos_tensao)]
    m["motor"] = [
        ROTULO_COMPONENTE[linha.idxmax()] if linha.notna().any() else "—"
        for _, linha in componentes_tensao.iterrows()
    ]
    for nome in comp.columns:
        m[f"z_{nome}"] = comp[nome]
    return m.sort_values("tensao", ascending=False)


CAUSA_SALARIAL = "Salarial"
CAUSA_QUALIFICACAO = "Qualificação"
CAUSA_RETENCAO = "Retenção"
LIMIAR_GAP_ESCOLARIDADE = -0.10
NIVEIS_QUALIFICADOS = ("Técnico", "Superior")


def causas(linha: pd.Series, *, saida_ref: float, fracao_tecnica: float = 0.0) -> list[str]:
    """Selos de causa de uma unidade (PLANEJAMENTO §7.2), a partir das métricas.

    - Salarial: gap de reposição < 0,95 (com amostra salarial suficiente).
    - Qualificação: gap de escolaridade ≤ −0,10 numa unidade em que Técnico +
      Superior somam ao menos metade das movimentações.
    - Retenção: saída voluntária ≥ referência + 5 p.p. com gap ≥ 1.
    """
    selos = []
    gap = linha.get(M_GAP_SAL)
    if pd.notna(gap) and gap < LIMIAR_COMPRESSAO:
        selos.append(CAUSA_SALARIAL)
    gap_esc = linha.get(M_GAP_ESC)
    if pd.notna(gap_esc) and gap_esc <= LIMIAR_GAP_ESCOLARIDADE and fracao_tecnica >= 0.5:
        selos.append(CAUSA_QUALIFICACAO)
    saida = linha.get(M_SAIDA_VOL)
    if pd.notna(saida) and pd.notna(gap) and saida >= saida_ref + 0.05 and gap >= 1:
        selos.append(CAUSA_RETENCAO)
    return selos


def fracao_por_nivel(df: pd.DataFrame, por: list[str], niveis: tuple[str, ...]) -> pd.Series:
    """Fração das movimentações de cada grupo que está nos `niveis` dados."""
    mov = df[COLUNA_ADMISSOES] + df[COLUNA_DESLIGAMENTOS]
    no_nivel = mov.where(df[COLUNA_NIVEL_QUALIFICACAO].astype(str).isin(niveis), 0)
    chave = [df[c] for c in por]
    soma_nivel = no_nivel.groupby(chave, observed=True).sum()
    soma = mov.groupby(chave, observed=True).sum()
    return (soma_nivel / soma.where(soma > 0)).fillna(0.0)


# ---------------------------------------------------------------------------
# Motor de recomendações (PLANEJAMENTO §9, adaptado aos dados disponíveis)
# ---------------------------------------------------------------------------


@dataclass
class Recomendacao:
    """Uma recomendação disparada por regra, com a evidência que a sustenta."""

    regiao: str
    macrofamilia: str
    alavanca: str
    regra: str
    evidencia: str
    nivel_alvo: str
    severidade: float
    movimentacoes: float
    prioridade: float = 0.0
    extras: dict = field(default_factory=dict)


ALAVANCA_SALARIO = "Revisar faixas salariais de entrada"
ALAVANCA_FORMACAO = "Formação técnica e parcerias de qualificação"
ALAVANCA_MOBILIDADE = "Recrutamento inter-regional e mobilidade"
ALAVANCA_AUTOMACAO = "Automação e redesenho de postos"
ALAVANCA_RETENCAO = "Retenção não salarial"


def gerar_recomendacoes(
    df: pd.DataFrame,
    *,
    mediana_regional: dict[tuple[str, str], float] | None = None,
) -> list[Recomendacao]:
    """Avalia as 5 regras por mesorregião × macrofamília (com guarda de amostra).

    As referências ("alta") são o valor do próprio recorte filtrado inteiro —
    o "estado" na seleção atual —, para que o critério se explique sozinho:
    "saída voluntária 58% vs 47% no recorte".
    """
    if df is None or df.empty:
        return []
    mediana_regional = mediana_regional or {}
    ref = total(df)
    saida_ref = ref[M_SAIDA_VOL]
    por = [COLUNA_REGIAO, COLUNA_MACROFAMILIA_CBO]
    m = matriz_diagnostico(df, por)
    if m.empty:
        return []
    frac_basico = fracao_por_nivel(df, por, ("Básico",))
    frac_tecnica = fracao_por_nivel(df, por, NIVEIS_QUALIFICADOS)
    nivel_dominante = _nivel_dominante(df, por)

    # Saldo por região × macrofamília, só de unidades com amostra (mobilidade).
    saldo_por = {(str(r_), str(m_)): float(s_) for r_, m_, s_ in
                 zip(m[COLUNA_REGIAO], m[COLUNA_MACROFAMILIA_CBO], m[M_SALDO])}
    recs: list[Recomendacao] = []
    for _, u in m.iterrows():
        chave = (u[COLUNA_REGIAO], u[COLUNA_MACROFAMILIA_CBO])
        regiao, macro = str(chave[0]), str(chave[1])
        nivel = nivel_dominante.get(chave, "—")
        mov = float(u[M_MOV])
        saida, gap = u[M_SAIDA_VOL], u[M_GAP_SAL]

        def add(alavanca, regra, evidencia, severidade, alvo=nivel, **extras):
            recs.append(Recomendacao(regiao, macro, alavanca, regra, evidencia, alvo,
                                     float(severidade), mov, extras=extras))

        if pd.notna(gap) and gap < LIMIAR_COMPRESSAO and pd.notna(saida) and saida >= saida_ref + 0.05:
            ref_sal = mediana_regional.get(chave)
            texto_ref = f"; mediana regional de admissão {fmt_brl(ref_sal)}" if ref_sal else ""
            add(ALAVANCA_SALARIO,
                f"salário de entrada mais de {fmt_gap(LIMIAR_COMPRESSAO).split()[0]} abaixo do de saída e saída voluntária ≥ referência + 5 p.p.",
                f"quem entra ganha {fmt_gap(gap)} de quem saiu; saída voluntária {fmt_pct(saida)} vs {fmt_pct(saida_ref)} no recorte{texto_ref}",
                (LIMIAR_COMPRESSAO - gap) / LIMIAR_COMPRESSAO + (saida - saida_ref))
        f_tec = float(frac_tecnica.get(chave, 0.0))
        if pd.notna(u[M_GAP_ESC]) and u[M_GAP_ESC] <= LIMIAR_GAP_ESCOLARIDADE and f_tec >= 0.5:
            add(ALAVANCA_FORMACAO,
                f"gap de escolaridade ≤ {fmt_num(LIMIAR_GAP_ESCOLARIDADE, 2)} em macrofamília técnica (Técnico + Superior ≥ 50%)",
                f"gap de escolaridade {fmt_num(u[M_GAP_ESC], 2)}; {fmt_pct(f_tec)} das movimentações em nível Técnico/Superior",
                -u[M_GAP_ESC], alvo="Técnico/Superior")
        if u["quadrante"] == Q_PRESSAO and u[M_SALDO] > 0:
            retracao = {r_: s_ for (r_, m_), s_ in saldo_por.items() if m_ == macro and r_ != regiao and s_ < 0}
            if retracao:
                origem = min(retracao, key=retracao.get)
                add(ALAVANCA_MOBILIDADE,
                    "expansão sob pressão aqui e retração da mesma macrofamília em outra mesorregião",
                    f"saldo {fmt_int(u[M_SALDO])} aqui; {origem} com saldo {fmt_int(retracao[origem])} na mesma macrofamília",
                    float(u[M_SALDO_REL]), origem=origem)
        f_bas = float(frac_basico.get(chave, 0.0))
        # Sem a taxa de reposição (função exata do saldo relativo, M1.C2), a
        # regra fica com o que ela media: mão de obra básica sem expansão.
        if f_bas >= 0.5 and u[M_SALDO] <= 0:
            add(ALAVANCA_AUTOMACAO,
                "nível Básico ≥ 50% e saldo ≤ 0",
                f"{fmt_pct(f_bas)} em nível Básico; saldo {fmt_int(u[M_SALDO])}",
                f_bas - 0.5, alvo="Básico")
        if pd.notna(saida) and saida >= saida_ref + 0.05 and pd.notna(gap) and gap >= 1:
            add(ALAVANCA_RETENCAO,
                "saída voluntária ≥ referência + 5 p.p. com gap de reposição ≥ 1 (salário não explica)",
                f"saída voluntária {fmt_pct(saida)} vs {fmt_pct(saida_ref)}; quem entra ganha {fmt_gap(gap)} de quem saiu",
                saida - saida_ref)
    for r in recs:
        r.prioridade = r.severidade * r.movimentacoes
    return sorted(recs, key=lambda r: r.prioridade, reverse=True)


def _nivel_dominante(df: pd.DataFrame, por: list[str]) -> dict:
    """Nível de qualificação com mais movimentações em cada grupo."""
    mov = (df[COLUNA_ADMISSOES] + df[COLUNA_DESLIGAMENTOS]).rename("mov")
    tabela = pd.concat([df[por + [COLUNA_NIVEL_QUALIFICACAO]].astype(str), mov], axis=1)
    soma = tabela.groupby(por + [COLUNA_NIVEL_QUALIFICACAO])["mov"].sum().reset_index()
    soma = soma.sort_values("mov", ascending=False).drop_duplicates(por)
    return {tuple(linha[por]): linha[COLUNA_NIVEL_QUALIFICACAO] for _, linha in soma.iterrows()}


def mediana_ponderada(valores: pd.Series, pesos: pd.Series) -> float:
    """Mediana de `valores` ponderada por `pesos` (NaN e peso 0 ignorados)."""
    dados = pd.DataFrame({"v": valores, "p": pesos}).dropna()
    dados = dados[dados["p"] > 0].sort_values("v")
    if dados.empty:
        return float("nan")
    acumulado = dados["p"].cumsum()
    return float(dados.loc[acumulado >= dados["p"].sum() / 2, "v"].iloc[0])


def medianas_perfil(perfil: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """Medianas salariais de um recorte do perfil, por `por`.

    As medianas não são somáveis: ao juntar várias células do perfil, usamos a
    mediana das medianas ponderada pelo número de salários (aproximação
    declarada na tela e na metodologia).
    """
    linhas = []
    for chave, g in perfil.groupby(por, observed=True):
        chave = chave if isinstance(chave, tuple) else (chave,)
        linhas.append({
            **dict(zip(por, chave)),
            "mediana_admissao": mediana_ponderada(g[COLUNA_MEDIANA_SALARIO_ADMISSAO], g["n_salario_admissao"]),
            "mediana_desligamento": mediana_ponderada(g[COLUNA_MEDIANA_SALARIO_DESLIGAMENTO], g["n_salario_desligamento"]),
            "n_admissao": int(g["n_salario_admissao"].sum()),
            "n_desligamento": int(g["n_salario_desligamento"].sum()),
        })
    return pd.DataFrame(linhas, columns=[*por, "mediana_admissao", "mediana_desligamento", "n_admissao", "n_desligamento"])


# ---------------------------------------------------------------------------
# Formatação pt-BR
# ---------------------------------------------------------------------------

_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _vazio(valor) -> bool:
    return valor is None or (isinstance(valor, float) and math.isnan(valor)) or pd.isna(valor)


def fmt_num(valor, casas: int = 0) -> str:
    """1234.5 → "1.234,5"; NaN → "—"."""
    if _vazio(valor):
        return "—"
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def fmt_int(valor) -> str:
    """Inteiro com separador de milhar e sinal de menos tipográfico."""
    return fmt_num(valor, 0).replace("-", "−")


def fmt_pct(valor, casas: int = 1) -> str:
    """0.471 → "47,1%"."""
    return "—" if _vazio(valor) else f"{fmt_num(float(valor) * 100, casas)}%"


def fmt_pp(valor, casas: int = 1) -> str:
    """Pontos percentuais com sinal: 2.3 → "+2,3 p.p."."""
    if _vazio(valor):
        return "—"
    sinal = "+" if valor > 0 else ("−" if valor < 0 else "")
    return f"{sinal}{fmt_num(abs(valor), casas)} p.p."


def fmt_brl(valor) -> str:
    """2345.6 → "R$ 2.346"."""
    return "—" if _vazio(valor) else f"R$ {fmt_num(valor, 0)}"


def fmt_razao(valor, casas: int = 2) -> str:
    """0.951 → "0,95"."""
    return fmt_num(valor, casas)


def fmt_gap(valor) -> str:
    """Razão admissão ÷ desligamento em palavras: 0,94 → "6% abaixo"; 1,03 → "3% acima"."""
    if _vazio(valor):
        return "—"
    pct = round((float(valor) - 1) * 100)
    if pct == 0:
        return "±0%"
    return f"{abs(pct)}% {'abaixo' if pct < 0 else 'acima'}"


def fmt_metrica(nome: str, valor) -> str:
    """Formata `valor` segundo o formato da métrica em `DEFINICOES`."""
    formato = DEFINICOES[nome].formato if nome in DEFINICOES else "num1"
    return {
        "int": fmt_int,
        "pct": fmt_pct,
        "razao": fmt_razao,
        "gap": fmt_gap,
        "brl": fmt_brl,
        "num1": lambda v: fmt_num(v, 1).replace("-", "−"),
        "num2": lambda v: fmt_num(v, 2).replace("-", "−"),
        "pp": fmt_pp,
    }[formato](valor)


def rotulo_mes(competencia) -> str:
    """"202509" → "set/25"."""
    texto = str(competencia)
    if len(texto) != 6 or not texto.isdigit():
        return texto
    return f"{_MESES[int(texto[4:]) - 1]}/{texto[2:4]}"


# ---------------------------------------------------------------------------
# Tema visual: cores semânticas (Okabe-Ito, seguras para daltonismo) e Plotly
# ---------------------------------------------------------------------------

COR_TENSAO = "#D55E00"    # vermelhão: tensão / apagão
COR_EXPANSAO = "#0072B2"  # azul: expansão
COR_NEUTRA = "#8C8C8C"    # cinza: neutro ou amostra insuficiente
COR_DESTAQUE = "#0F4C81"  # cor de marca (acento do tema)
CORES_QUADRANTE = {
    Q_SAUDAVEL: COR_EXPANSAO,
    Q_PRESSAO: "#E69F00",
    Q_ESTAGNACAO: COR_NEUTRA,
    Q_APAGAO: COR_TENSAO,
}
PALETA_CATEGORICA = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000", "#999999", "#882255", "#44AA99", "#117733"]
ESCALA_DIVERGENTE = [[0.0, COR_TENSAO], [0.5, "#F2F2F2"], [1.0, COR_EXPANSAO]]
ESCALA_TENSAO = [[0.0, "#FBE3D6"], [1.0, COR_TENSAO]]
# Classes do mapa: sequencial verde-água → azul (claro → escuro) e divergente
# simétrica (tensão ← neutro → expansão), cinza fica reservado a "sem dado".
CLASSES_SEQUENCIAL = ["#A6DBC8", "#47B5C2", "#2B7FBF", "#1B4F72"]
CLASSES_DIVERGENTE = ["#D55E00", "#EC9A66", "#F7D6C1", "#C6DCEE", "#62A0D2", "#0072B2"]
TEMPLATE = "sc_painel"


def registrar_template() -> str:
    """Registra (uma vez) o template Plotly do painel e o torna padrão."""
    import plotly.graph_objects as go
    import plotly.io as pio

    if TEMPLATE not in pio.templates:
        base = go.layout.Template(pio.templates["plotly_white"])
        base.layout.font = {"size": 15, "family": "Inter, Segoe UI, sans-serif"}
        base.layout.title = {"font": {"size": 18}, "x": 0, "xanchor": "left"}
        base.layout.colorway = PALETA_CATEGORICA
        base.layout.hoverlabel = {"font": {"size": 14}}
        base.layout.legend = {"font": {"size": 14}}
        base.layout.margin = {"l": 10, "r": 10, "t": 60, "b": 10}
        base.layout.separators = ",."
        base.layout.paper_bgcolor = "rgba(0,0,0,0)"
        base.layout.plot_bgcolor = "rgba(0,0,0,0)"
        grade = {"gridcolor": "rgba(128,128,128,.18)", "zerolinecolor": "rgba(128,128,128,.35)"}
        base.layout.xaxis.update(grade)
        base.layout.yaxis.update(grade)
        pio.templates[TEMPLATE] = base
    pio.templates.default = TEMPLATE
    return TEMPLATE


def figura_vazia(mensagem: str):
    """Figura de *empty-state* com uma anotação central (nunca levanta)."""
    import plotly.graph_objects as go

    registrar_template()
    figura = go.Figure()
    figura.update_layout(
        xaxis={"visible": False}, yaxis={"visible": False}, height=260,
        annotations=[{"text": mensagem, "xref": "paper", "yref": "paper", "x": 0.5,
                      "y": 0.5, "showarrow": False, "font": {"size": 15}}],
    )
    return figura


def carregar_geojson(caminho: str | Path | None = None) -> dict | None:
    """Malha GeoJSON dos municípios de SC, ou ``None`` se ausente/ilegível."""
    try:
        with Path(caminho or CAMINHO_GEOJSON).open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, ValueError):
        return None


def carregar_cbo() -> tuple[pd.DataFrame | None, pd.DataFrame | None, str | None]:
    """Classificação da IA, divergências entre rodadas e prompt (cópias locais)."""
    def _ler(caminho, leitor):
        try:
            return leitor(caminho)
        except Exception:  # noqa: BLE001
            return None
    mapa = _ler(CAMINHO_CBO, lambda c: pd.read_csv(c, dtype={"cbo2002ocupação": str}))
    div = _ler(CAMINHO_DIVERGENCIAS, lambda c: pd.read_csv(c, dtype={"cbo2002ocupação": str}))
    prompt = _ler(CAMINHO_PROMPT, lambda c: Path(c).read_text(encoding="utf-8"))
    return mapa, div, prompt



# ---------------------------------------------------------------------------
# Camada Streamlit (import tardio): contexto, filtros, cartões e proteção
# ---------------------------------------------------------------------------


@dataclass
class Contexto:
    """O que cada página recebe: artefatos, filtros e os recortes já prontos."""

    art: Artefatos
    filtros: Filtros
    df: pd.DataFrame          # agregado com todos os filtros
    ref: pd.DataFrame         # só escopo + período: a referência "SC"

    @property
    def tem_recorte(self) -> bool:
        f = self.filtros
        return bool(f.territorios or f.setores or f.macrofamilias or f.niveis)


_CHAVES_FILTRO = ("f_escopo", "f_meses", "f_nivel", "f_terr", "f_setor", "f_macro", "f_niv")


def carregar_artefatos_cache() -> Artefatos:
    """`carregar_artefatos` com cache compartilhado (sem cópia por execução)."""
    import streamlit as st

    @st.cache_resource(ttl=TTL_CACHE_DADOS, show_spinner="Carregando dados agregados…")
    def _carregar() -> Artefatos:
        return carregar_artefatos()

    return _carregar()


def geojson_cache() -> dict | None:
    import streamlit as st

    @st.cache_resource
    def _ler() -> dict | None:
        return carregar_geojson()

    return _ler()


def cbo_cache():
    import streamlit as st

    @st.cache_resource
    def _ler():
        return carregar_cbo()

    return _ler()


def _meses(df: pd.DataFrame) -> list[str]:
    return sorted(df[COLUNA_MES].astype(str).unique())


def limpar_filtros(df: pd.DataFrame | None = None) -> None:
    """Volta todos os filtros ao padrão (indústria, período inteiro)."""
    import streamlit as st

    for chave in _CHAVES_FILTRO:
        st.session_state.pop(chave, None)


def _opcoes(df: pd.DataFrame, coluna: str) -> list[str]:
    return sorted(str(v) for v in df[coluna].dropna().unique())


def barra_lateral(df: pd.DataFrame) -> Filtros:
    """Filtros globais na barra lateral, persistidos em `st.session_state`."""
    import streamlit as st

    meses = _meses(df)
    estado = st.session_state
    estado.setdefault("f_escopo", ESCOPO_INDUSTRIA)
    estado.setdefault("f_meses", (meses[0], meses[-1]))
    estado.setdefault("f_nivel", NIVEL_MESO)
    if tuple(estado["f_meses"])[0] not in meses or tuple(estado["f_meses"])[1] not in meses:
        estado["f_meses"] = (meses[0], meses[-1])

    lateral = st.sidebar
    lateral.markdown("### Filtros")
    lateral.radio("Escopo", [ESCOPO_INDUSTRIA, ESCOPO_ECONOMIA], key="f_escopo",
                  help="Indústria = seções CNAE B a F (extrativa, transformação, "
                       "eletricidade e gás, água e resíduos, construção).")
    lateral.select_slider("Período", options=meses, key="f_meses", format_func=rotulo_mes)
    lateral.radio("Nível territorial", [NIVEL_MESO, NIVEL_MICRO, NIVEL_MUNICIPIO], key="f_nivel",
                  horizontal=True, on_change=lambda: estado.update(f_terr=[]))

    escopo_df = df[df[COLUNA_ESCOPO_INDUSTRIAL]] if estado["f_escopo"] == ESCOPO_INDUSTRIA else df
    coluna_terr = COLUNA_POR_NIVEL_TERRITORIAL[estado["f_nivel"]]
    for chave, coluna in (("f_terr", coluna_terr), ("f_setor", COLUNA_SETOR),
                          ("f_macro", COLUNA_MACROFAMILIA_CBO), ("f_niv", COLUNA_NIVEL_QUALIFICACAO)):
        validas = set(_opcoes(escopo_df, coluna))
        estado[chave] = [v for v in estado.get(chave, []) if v in validas]
    lateral.multiselect(estado["f_nivel"], _opcoes(escopo_df, coluna_terr), key="f_terr",
                        placeholder="Todo o estado")
    lateral.multiselect("Setor", _opcoes(escopo_df, COLUNA_SETOR), key="f_setor", placeholder="Todos",
                        help="Na indústria de transformação (C), o setor é a divisão CNAE agrupada.")
    lateral.multiselect("Macrofamília (IA)", _opcoes(escopo_df, COLUNA_MACROFAMILIA_CBO), key="f_macro",
                        placeholder="Todas")
    ordem_niveis = ["Básico", "Qualificado", "Técnico", "Superior"]
    niveis = sorted(_opcoes(escopo_df, COLUNA_NIVEL_QUALIFICACAO),
                    key=lambda v: ordem_niveis.index(v) if v in ordem_niveis else 9)
    lateral.multiselect("Nível de qualificação (IA)", niveis, key="f_niv", placeholder="Todos")
    lateral.button("Limpar filtros", on_click=limpar_filtros, icon=":material/filter_alt_off:",
                   width="stretch")

    return Filtros(
        escopo=estado["f_escopo"], meses=tuple(estado["f_meses"]), nivel_territorial=estado["f_nivel"],
        territorios=tuple(estado["f_terr"]), setores=tuple(estado["f_setor"]),
        macrofamilias=tuple(estado["f_macro"]), niveis=tuple(estado["f_niv"]),
    )


def montar_contexto(art: Artefatos, filtros: Filtros, filtrador=None) -> Contexto:
    """Aplica os filtros uma vez por execução; as páginas só leem o resultado.

    ``filtrador(filtros)`` permite trocar `filtrar` por uma versão em cache
    compartilhada entre sessões (o recorte é somente leitura).
    """
    filtrador = filtrador or (lambda f: filtrar(art.agregado, f))
    referencia = Filtros(escopo=filtros.escopo, meses=filtros.meses)
    ref = filtrador(referencia)
    df = ref if filtros == referencia else filtrador(filtros)
    return Contexto(art, filtros, df, ref)


def montar_contexto_cache(art: Artefatos, filtros: Filtros) -> Contexto:
    """`montar_contexto` com os recortes em cache compartilhado (memória do B1)."""
    import streamlit as st

    @st.cache_resource(ttl=TTL_CACHE_DADOS, max_entries=24, show_spinner=False)
    def _filtrar(art_id: int, f: Filtros) -> pd.DataFrame:
        return filtrar(art.agregado, f)

    return montar_contexto(art, filtros, lambda f: _filtrar(id(art.agregado), f))


def contexto_padrao(art: Artefatos) -> Contexto:
    """Contexto com os filtros padrão (usado no modo apresentação)."""
    return montar_contexto(art, Filtros(meses=tuple(_meses(art.agregado)[i] for i in (0, -1))))


# Tokens do visual institucional; o tema vem de `st.context.theme` (segue o
# menu Settings do Streamlit, não só a preferência do sistema).
_TOKENS = {
    "light": {"texto": "#1B2430", "suave": "#56636F", "painel": "#E8ECEF", "painel-forte": "#D9DFE4",
              "linha": "#CDD3D8", "tema": "#1A5F79", "destaque": "#2E9BC6", "laranja": "#F7941D",
              "laranja-texto": "#A65400", "bom": "#1E7B34", "ruim": "#B3261E", "cartao": "#FFFFFF",
              "foco": "#1F6E8C"},
    "dark": {"texto": "#E6EDF3", "suave": "#A7B3BF", "painel": "#1A2430", "painel-forte": "#243142",
             "linha": "#2E3B4C", "tema": "#7FCDE6", "destaque": "#6FC3E3", "laranja": "#F7941D",
             "laranja-texto": "#F7A84A", "bom": "#6CCB8A", "ruim": "#FF8A80", "cartao": "#0F1720",
             "foco": "#7FCDE6"},
}

_CSS = """
/* Barra lateral: trilha + título + lista plana de páginas */
.rx-trilha {margin: 0; font-size: .85rem; opacity: .9;}
.rx-titulo {margin: 0 0 .25rem; font-size: 1.5rem; font-weight: 700; line-height: 1.15;}
[data-testid="stSidebar"] [data-testid="stPageLink"] {margin: 0;}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
  border-radius: 0; padding: .7rem 2rem; margin: 0 -2rem; width: calc(100% + 4rem);
  border-bottom: 1px solid rgba(255,255,255,.18);
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {background: rgba(255,255,255,.10);}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p {font-size: 1rem; color: #FFFFFF;}
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {border: 1.5px solid #FFFFFF;}
[data-testid="stSidebar"] [data-testid="stMultiSelectTagsContainer"] [data-tag],
[data-testid="stSidebar"] [data-testid="stMultiSelectTagsContainer"] [data-tag] * {color: #164E63;}
[data-testid="stSidebar"] :focus-visible {outline: 2px solid #FFFFFF !important; outline-offset: 2px;}

/* Foco visível no conteúdo */
[data-testid="stMain"] :focus-visible {outline: 2px solid var(--rx-foco) !important; outline-offset: 2px;}

/* Títulos institucionais, sem sombra, borda fina */
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3 {font-weight: 700; letter-spacing: 0;}
[data-testid="stMain"] hr {border: 0; border-top: 3px solid var(--rx-laranja); margin: 2rem 0 1rem;}

/* Coluna de indicadores em sanfona */
.st-key-rx-indicadores {background: var(--rx-painel); padding: .25rem 0 .75rem; gap: 0;}
.st-key-rx-indicadores [data-testid="stExpander"] details {border: 0; border-radius: 0; background: transparent;}
.st-key-rx-indicadores [data-testid="stExpander"] summary {
  background: var(--rx-painel); border-bottom: 1px solid var(--rx-linha); border-radius: 0; padding: .8rem 1rem;
}
.st-key-rx-indicadores [data-testid="stExpander"] details[open] > summary {background: var(--rx-painel-forte);}
.st-key-rx-indicadores [data-testid="stExpander"] summary p,
.st-key-rx-indicadores [data-testid="stExpander"] summary span {
  color: var(--rx-tema); font-weight: 700; text-transform: uppercase; font-size: 1.02rem;
}
.st-key-rx-indicadores [data-testid="stExpanderDetails"] {padding: 0 1rem .5rem 1rem;}
.rx-linha {
  display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: .25rem 1rem; align-items: center;
  padding: .55rem 0 .55rem 1.5rem; border-bottom: 1px solid var(--rx-linha); color: var(--rx-texto);
}
.rx-linha:last-child {border-bottom: 0;}
.rx-rotulo {font-size: .95rem;}
.rx-periodo {white-space: nowrap;}
.rx-valor b {font-size: 1.2rem; font-weight: 700;}
.rx-valor small {color: var(--rx-suave); font-size: .85rem;}
.rx-delta {display: block; font-size: .8rem; margin-top: .1rem;}
.rx-bom {color: var(--rx-bom);}
.rx-ruim {color: var(--rx-ruim);}
@media (max-width: 640px) {
  .rx-linha {grid-template-columns: 1fr; padding-left: .5rem;}
}

/* Cartão de destaque: topo laranja, número grande em azul-claro, régua de ranking */
.st-key-rx-destaque, [class*="-ativo"][class*="st-key-rx-achado-"] {border-top: 4px solid var(--rx-laranja) !important;}
.rx-destaque {color: var(--rx-texto); max-width: 34rem;}
.rx-d-rotulo {font-weight: 700; font-size: 1.05rem;}
.rx-d-valor {color: var(--rx-destaque); font-size: 2.4rem; font-weight: 700; line-height: 1.2;}
.rx-d-valor span {font-size: 1rem;}
.rx-d-comp {margin-top: 1rem; font-size: 1.15rem;}
.rx-d-nivel {margin-top: .75rem;}
.rx-regua {max-width: 18rem; margin: .25rem 0 1.6rem;}
.rx-extremos {display: flex; justify-content: space-between; font-weight: 700; font-size: .85rem;}
.rx-trilho {
  position: relative; height: 12px; margin-top: .2rem;
  border-left: 1px solid var(--rx-suave); border-right: 1px solid var(--rx-suave);
  background: linear-gradient(var(--rx-suave), var(--rx-suave)) center / 100% 1px no-repeat,
              repeating-linear-gradient(90deg, var(--rx-suave) 0 1px, transparent 1px 10%) center / 100% 6px no-repeat;
}
.rx-marca {position: absolute; top: -3px; width: 7px; height: 18px; margin-left: -3.5px; background: var(--rx-laranja);}
.rx-marca em {position: absolute; top: 19px; left: 50%; transform: translateX(-50%);
  font-style: normal; font-weight: 700; font-size: .85rem; color: var(--rx-laranja-texto);}
.rx-d-nota {color: var(--rx-suave); font-size: .85rem; margin: 0;}

/* Cartões de alerta do Diagnóstico: faixa à esquerda na cor do quadrante + rótulo (nunca só cor) */
[class*="st-key-rx-alerta-"] {border-left: 6px solid var(--rx-suave) !important;}
[class*="st-key-rx-alerta-apagao"] {border-left-color: #D55E00 !important;}
[class*="st-key-rx-alerta-pressao"] {border-left-color: #E69F00 !important;}
.rx-semaforo {display: inline-flex; align-items: center; gap: .4rem; font-weight: 700; font-size: .9rem; color: var(--rx-texto);}
.rx-semaforo::before {content: ""; width: .8rem; height: .8rem; border-radius: 50%; background: currentColor;}
.rx-semaforo.rx-apagao::before {background: #D55E00;}
.rx-semaforo.rx-pressao::before {background: #E69F00;}
"""


def estilo_global() -> None:
    """Injeta o CSS do painel (uma vez por execução, em `app.py`)."""
    import streamlit as st

    tipo = getattr(getattr(st.context, "theme", None), "type", None) or "light"
    tokens = "".join(f"--rx-{k}: {v};" for k, v in _TOKENS.get(tipo, _TOKENS["light"]).items())
    st.html(f"<style>:root {{{tokens}}}{_CSS}</style>")


def cabecalho(ctx: Contexto) -> None:
    """Linha de filtros ativos e procedência dos dados, no topo de cada página."""
    import streamlit as st

    meta = ctx.art.metadados or {}
    origem = {"blob": "Azure Blob", "local": "cópia local"}.get(ctx.art.origem, "—")
    gerado = str(meta.get("gerado_em", ""))[:16].replace("T", " ")
    st.caption(f":material/filter_alt: {ctx.filtros.descricao()}  ·  :material/database: {origem}"
               + (f", gerado em {gerado}" if gerado else ""))
    for aviso in ctx.art.avisos:
        if "schema antigo" in aviso or "ilegível" in aviso:
            st.warning(aviso, icon=":material/warning:")


def delta_texto(nome: str, valor: float, referencia: float, sufixo: str) -> str | None:
    """Delta pt-BR de uma métrica vs referência ("+2,3 p.p. vs SC")."""
    if _vazio(valor) or _vazio(referencia):
        return None
    formato = DEFINICOES[nome].formato
    diff = float(valor) - float(referencia)
    if formato == "pct":
        texto = f"{fmt_num(abs(diff) * 100, 1)} p.p."
    elif formato == "int":
        texto = fmt_num(abs(diff), 0)
    elif formato == "razao":
        texto = fmt_num(abs(diff), 2)
    elif formato == "gap":
        texto = f"{fmt_num(abs(diff) * 100, 0)} p.p."
    elif formato == "brl":
        texto = f"R$ {fmt_num(abs(diff), 0)}"
    elif formato == "pp":
        texto = f"{fmt_num(abs(diff), 1)} p.p."
    else:
        texto = fmt_num(abs(diff), 2 if formato == "num2" else 1)
    return f"{'-' if diff < 0 else '+'}{texto} {sufixo}"


# Métricas em que subir é ruim (delta em vermelho quando sobe).
METRICAS_INVERSAS = {M_SAIDA_VOL}


# Temas da coluna de indicadores (sanfona do Panorama): título, ícone e métricas.
TEMAS_KPI = [
    ("Movimentação", ":material/swap_horiz:", [M_MOV, M_SALDO, M_SALDO_10K]),
    ("Renda", ":material/payments:", [M_GAP_SAL, M_SAL_ADM, M_SAL_DESL]),
    ("Escolaridade", ":material/school:", [M_GAP_ESC]),
    ("Tensão", ":material/crisis_alert:", [M_SAIDA_VOL]),
]
METRICAS_TEMAS = [m for _, _, ms in TEMAS_KPI for m in ms]

# Unidade por extenso, em cinza sob/ao lado do valor.
UNIDADES = {
    M_MOV: "admissões + desligamentos",
    M_SALDO: "vagas",
    M_SALDO_10K: "vagas por 10 mil hab.",
    M_SALDO_REL: "do total movimentado",
    M_SAIDA_VOL: "dos desligamentos, a pedido",
    M_GAP_SAL: "do salário de quem saiu",
    M_SAL_ADM: "por mês",
    M_SAL_DESL: "por mês",
    M_GAP_ESC: "níveis (negativo = entra gente menos escolarizada)",
}


def _periodo(ctx: Contexto) -> str:
    meses = ctx.filtros.meses
    return f"[{rotulo_mes(meses[0])}–{rotulo_mes(meses[1])}]" if meses else ""


def cartoes_kpi(ctx: Contexto, metricas: list[str] | None = None) -> None:
    """Indicadores agrupados por tema (sanfona), com fórmula e, havendo recorte, delta vs estado."""
    import html

    import streamlit as st

    metricas = metricas or KPIS_PADRAO
    atual = total(ctx.df)
    # Sem recorte não há com o que comparar: o delta semestral media calendário (M1.C3).
    ref = total(ctx.ref) if ctx.tem_recorte else None
    periodo = html.escape(_periodo(ctx))

    def _linha(nome: str) -> str:
        definicao = DEFINICOES[nome]
        ajuda = definicao.formula
        if nome == M_GAP_SAL and not atual[M_SALARIO_OK]:
            ajuda += " — amostra salarial insuficiente nesta seleção."
        delta = None if ref is None else delta_texto(nome, atual[nome], ref[nome], "vs estado")
        extra = ""
        if delta:
            subiu = delta.startswith("+")
            bom = subiu != (nome in METRICAS_INVERSAS)
            extra = (f'<span class="rx-delta {"rx-bom" if bom else "rx-ruim"}">'
                     f'{"↑" if subiu else "↓"} {html.escape(delta)}</span>')
        return (f'<div class="rx-linha" title="{html.escape(ajuda)}">'
                f'<span class="rx-rotulo">{html.escape(definicao.rotulo)} <span class="rx-periodo">{periodo}</span></span>'
                f'<span class="rx-valor"><b>{html.escape(fmt_metrica(nome, atual[nome]))}</b> '
                f'<small>{html.escape(UNIDADES.get(nome, ""))}</small>{extra}</span></div>')

    # No máximo 4 principais abertos; o resto, por tema, fica recolhido em "Aprofundar" (M3.C3).
    principais = [m for m in KPIS_PADRAO if m in metricas]
    restantes = [m for m in metricas if m not in METRICAS_TEMAS and m not in principais]
    temas = [(f"Aprofundar: {t.lower()}", i, [m for m in ms if m in metricas and m not in principais])
             for t, i, ms in TEMAS_KPI]
    temas += [("Aprofundar: outros", ":material/more_horiz:", restantes)] if restantes else []
    with st.container(key="rx-indicadores"):
        if principais:
            with st.expander("Principais", expanded=True, icon=":material/star:"):
                st.html("".join(_linha(n) for n in principais))
        for titulo, icone, nomes in temas:
            if nomes:
                with st.expander(titulo, expanded=False, icon=icone):
                    st.html("".join(_linha(n) for n in nomes))


def posicao_ranking(por: pd.DataFrame, coluna: str, metrica: str, alvo: str) -> tuple[int, int] | None:
    """Posição de `alvo` (1º = maior valor) entre as unidades com amostra suficiente."""
    validas = por[por[M_AMOSTRA_OK] & por[metrica].notna()]
    ordem = validas.sort_values(metrica, ascending=False, kind="stable")[coluna].astype(str).tolist()
    return (ordem.index(alvo) + 1, len(ordem)) if alvo in ordem else None


_PLURAL_NIVEL = {NIVEL_MESO: "mesorregiões", NIVEL_MICRO: "microrregiões", NIVEL_MUNICIPIO: "municípios"}


def cartao_destaque(ctx: Contexto, metrica: str) -> None:
    """Indicador em destaque com a régua de ranking do território filtrado."""
    import html

    import streamlit as st

    definicao = DEFINICOES[metrica]
    f = ctx.filtros
    valor = total(ctx.df)[metrica]
    partes = [
        f'<div class="rx-d-rotulo">{html.escape(definicao.rotulo)} {html.escape(_periodo(ctx))}</div>',
        f'<div class="rx-d-valor">{html.escape(fmt_metrica(metrica, valor))} '
        f'<span>{html.escape(UNIDADES.get(metrica, ""))}</span></div>',
        '<div class="rx-d-comp">Comparando a outras regiões</div>',
    ]
    plural = _PLURAL_NIVEL[f.nivel_territorial]
    rank = None
    if len(f.territorios) == 1:
        coluna = COLUNA_POR_NIVEL_TERRITORIAL[f.nivel_territorial]
        base = filtrar(ctx.art.agregado, f, ignorar=("territorio",))
        rank = posicao_ranking(agregar_metricas(base, [coluna]), coluna, metrica,
                               f.territorios[0])
    if rank:
        pos, n = rank
        x = 100.0 if n == 1 else (n - pos) / (n - 1) * 100
        partes.append(
            f'<div class="rx-d-nivel">Entre as {plural}</div>'
            f'<div class="rx-regua" role="img" aria-label="{pos}º de {n} {plural} (1º = maior valor)">'
            f'<div class="rx-extremos" aria-hidden="true"><span>{n}º</span><span>1º</span></div>'
            f'<div class="rx-trilho" aria-hidden="true"><span class="rx-marca" style="left:{x:.1f}%">'
            f'<em>{pos}º</em></span></div></div>'
            '<p class="rx-d-nota">1º = maior valor entre as unidades com amostra suficiente.</p>')
    elif len(f.territorios) == 1:
        partes.append('<p class="rx-d-nota">Sem amostra suficiente para ranquear este território.</p>')
    else:
        partes.append(f'<p class="rx-d-nota">Valor do estado. Filtre uma única '
                      f'{html.escape(f.nivel_territorial.lower())} na barra lateral para ver a posição '
                      f'dela entre as {plural}.</p>')
    st.html(f'<div class="rx-destaque">{"".join(partes)}</div>')


def baixar_csv(df: pd.DataFrame, nome: str, rotulo: str = "Baixar dados filtrados (CSV)") -> None:
    """Botão de download em CSV compatível com Excel pt-BR (; e vírgula decimal)."""
    import streamlit as st

    st.download_button(rotulo, df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=nome, mime="text/csv", icon=":material/download:")


def pagina_segura(nome: str, func: Callable[[Contexto], None]) -> Callable[[], None]:
    """Fronteira de erro: a página nunca mostra traceback, só o que falhou."""

    def _executar() -> None:
        import streamlit as st

        ctx: Contexto | None = st.session_state.get("_ctx")
        try:
            if ctx is None:
                raise RuntimeError("contexto de dados não inicializado")
            func(ctx)
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ in ("RerunException", "StopException"):
                raise
            origem = getattr(getattr(ctx, "art", None), "origem", None) or "nenhuma"
            obter_logger().exception("[%s] falha na página %s", _ETAPA, nome)
            st.error(
                f"Não foi possível montar a página **{nome}** ({type(exc).__name__}: {exc}). "
                f"Fonte de dados em uso: {origem}. As demais páginas seguem disponíveis.",
                icon=":material/error:",
            )

    _executar.__name__ = f"pagina_{nome}"
    return _executar
