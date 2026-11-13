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
    COLUNA_DESLIGAMENTOS_DESCONTADOS,
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
from src.rais import CHAVES_ESTOQUE, COLUNAS_ESTOQUE
from src.mapeamentos import NAO_CLASSIFICADO

# Rótulos e limiares de negócio: fonte única em `dashboard.regras` (regra 5 do
# plano da banca). Reexportados aqui para que `c.Q_APAGAO` etc. continuem valendo.
from dashboard.regras import (  # noqa: F401
    ALAVANCA_AUTOMACAO,
    ALAVANCA_FORMACAO,
    ALAVANCA_MOBILIDADE,
    ALAVANCA_RETENCAO,
    ALAVANCA_SALARIO,
    CAUSA_QUALIFICACAO,
    CAUSA_RETENCAO,
    CAUSA_SALARIAL,
    AJUDA_ESCOPO,
    CORES_QUADRANTE,
    ESCOPO_ECONOMIA,
    ESCOPO_INDUSTRIA,
    ESCOPO_PADRAO,
    ESCOPO_TRANSFORMACAO,
    CONTEXTO_SETOR,
    ESCOPOS,
    FRACAO_CONCENTRACAO_TEXTO,
    SETOR_NAVAL,
    SETOR_VEICULOS,
    FRACAO_CONSTRUCAO,
    NOME_ESCOPO,
    ROTULO_CONSTRUCAO,
    SECAO_CONSTRUCAO,
    SECAO_TRANSFORMACAO,
    inclui_construcao,
    LIMIAR_COMPRESSAO,
    LIMIAR_DESTAQUE_GAP_ESC,
    LIMIAR_FORMACAO_GAP_ESC,
    MACROFAMILIAS_FORA_FORMACAO,
    MARGEM_FORMACAO_TECNICO,
    N_CBOS_FORMACAO,
    NIVEIS_ALVO_FORMACAO,
    QUADRANTES_FORMACAO,
    FRACAO_META_DISTANCIA,
    HORIZONTE,
    KPI_ALAVANCA,
    KPI_RESERVA,
    PRAZO_META_MESES,
    QUEM_AGE,
    ACAO_ALAVANCA,
    REGRA_ALAVANCA,
    TOP_EXECUTIVO,
    CORR_EXPLICA,
    CORR_EXPLICA_PARTE,
    FRACAO_EXPLICA,
    FRACAO_EXPLICA_PARTE,
    veredito,
    LIMIAR_GAP_ESCOLARIDADE,
    MARGEM_SALARIAL_RELATIVA,
    MARGEM_SAIDA_VOLUNTARIA,
    MIN_MOVIMENTACOES,
    MIN_SALARIOS,
    NIVEIS_QUALIFICADOS,
    Q_APAGAO,
    Q_ESTAGNACAO,
    Q_EXPANSAO,
    Q_RETRACAO,
    QUADRANTES,
    QUADRANTES_ALERTA,
    quadrante,
    salario_nao_explica,
    salario_pior_que_estado,
    LIMIAR_CONCENTRACAO_MES,
    LIMIAR_CONCENTRACAO_MUNICIPIO,
    MIN_MESES_CONCENTRACAO,
    SELO_CONCENTRADA,
    expansao_concentrada,
    FAIXA_MEDIO,
    FAIXA_SUPERIOR,
    FAIXAS_MEDIO_OU_MAIS,
    FATOR_PREMIO_BAIXO,
    premio_baixo,
    MIN_MOV_PIOR_MUNICIPIO,
    CUSTO_REPOSICAO_MAX,
    CUSTO_REPOSICAO_MIN,
    CUSTO_REPOSICAO_PADRAO,
    FONTE_CUSTO_REPOSICAO,
    ALAVANCAS_OBSERVACAO,
    MOTIVO_OBSERVACAO,
    eh_observacao,
)

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
CAMINHO_META_RODADA2 = _DIR_DADOS / "cbo_macrofamilias_gemini.csv.meta.json"   # TAX-04: a classificação de auditoria

VAR_CREDENCIAL_AZURE = "AZURE_STORAGE_CONNECTION_STRING"
VAR_CONTAINER_AZURE = "AZURE_BLOB_CONTAINER"
CONTAINER_PADRAO = "caged-agregado"
NOME_BLOB_AGREGADO = "caged_agregado.parquet"
NOME_BLOB_PERFIL = "caged_perfil.parquet"
NOME_BLOB_METADADOS = "metadados.json"
NOME_BLOB_ESTOQUE = "rais_estoque.parquet"
NOME_BLOB_CBO = "caged_cbo.parquet"   # Lote B: tabela por ocupação (opcional)

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
    cbo: pd.DataFrame | None = None   # tabela por CBO (mesma origem do agregado)

    @property
    def disponivel(self) -> bool:
        return self.agregado is not None


# Colunas legadas (R6) que o painel v2 não lê: ficam no arquivo para o app
# antigo, mas não entram na memória do servidor.
_COLUNAS_LEGADAS = {
    "saldo_liquido", "saldo_por_10k", "turnover", "indice_aquecimento",
    "salario_medio_admissao", "salario_medio_desligamento", "escolaridade_media",
}


def _nomes_atuais(df: pd.DataFrame) -> pd.DataFrame:
    """TAX-03: aplica os aliases de macrofamília (nome antigo → atual) num artefato lido."""
    from src.mapeamentos import ALIASES_MACROFAMILIA

    if df is None or COLUNA_MACROFAMILIA_CBO not in df.columns:
        return df
    coluna = df[COLUNA_MACROFAMILIA_CBO]
    if isinstance(coluna.dtype, pd.CategoricalDtype):
        antigos = [a for a in ALIASES_MACROFAMILIA if a in coluna.cat.categories]
        if not antigos:
            return df
        coluna = coluna.astype(str)
    if not coluna.isin(list(ALIASES_MACROFAMILIA)).any():
        return df
    return df.assign(**{COLUNA_MACROFAMILIA_CBO: coluna.replace(ALIASES_MACROFAMILIA)})


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
    return _nomes_atuais(pq.read_table(fonte, columns=colunas, read_dictionary=textos).to_pandas())


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
        if agregado is not None and schema_v2_ok(agregado):
            try:
                estoque = _nomes_atuais(pd.read_parquet(pasta / NOME_BLOB_ESTOQUE))
            except Exception:  # noqa: BLE001
                estoque = None
            agregado = anexar_blocos(anexar_estoque(agregado, estoque, avisos))
        return agregado, perfil, meta

    credencial = (ambiente.get(VAR_CREDENCIAL_AZURE) or "").strip()
    if credencial:
        try:
            agregado = ler_parquet_enxuto(io.BytesIO(baixar(credencial, NOME_BLOB_AGREGADO)))
            if not schema_v2_ok(agregado):
                raise ValueError("a cópia do Blob está no schema antigo (sem as colunas v2)")
            perfil = ler_parquet_enxuto(io.BytesIO(baixar(credencial, NOME_BLOB_PERFIL)))
            meta = json.loads(baixar(credencial, NOME_BLOB_METADADOS).decode("utf-8"))
            estoque = _nomes_atuais(pd.read_parquet(io.BytesIO(baixar(credencial, NOME_BLOB_ESTOQUE))))
            agregado = anexar_blocos(anexar_estoque(agregado, estoque, avisos))
            try:
                cbo = ler_parquet_enxuto(io.BytesIO(baixar(credencial, NOME_BLOB_CBO)))
            except Exception:  # noqa: BLE001 — opcional: sem ela, as listas de CBO somem
                cbo = None
                avisos.append("Tabela por ocupação (CBO) indisponível no Blob.")
            return Artefatos(preparar_tipos(agregado), perfil, meta, "blob", tuple(avisos), cbo=cbo)
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
    try:
        cbo = ler_parquet_enxuto(pasta / NOME_BLOB_CBO)
    except Exception:  # noqa: BLE001
        cbo = None
        avisos.append("Tabela por ocupação (CBO) indisponível na cópia local.")
    return Artefatos(preparar_tipos(agregado), perfil, meta, "local", tuple(avisos), cbo=cbo)


def anexar_estoque(agregado: pd.DataFrame, estoque: pd.DataFrame | None, avisos: list[str]) -> pd.DataFrame:
    """Anexa a cada linha o estoque RAIS da sua célula (município × seção × setor × macro × nível).

    O valor se repete nas linhas mensais da célula, como a população: quem soma
    o estoque deduplica pela célula (`agregar_metricas`); ele não é aditivo.
    """
    if estoque is None or not set(CHAVES_ESTOQUE) <= set(agregado.columns):
        avisos.append("Estoque da RAIS indisponível: rotatividade e desligamento precoce ficam em branco.")
        return agregado
    return agregado.merge(estoque[CHAVES_ESTOQUE + COLUNAS_ESTOQUE], on=CHAVES_ESTOQUE, how="left")


# Blocos de 12 meses da janela de 24 (M5.C6): a aceleração compara os dois.
BLOCO_ANTERIOR = ("202409", "202508")
BLOCO_RECENTE = ("202509", "202608")
COLUNA_SALDO_ANTERIOR = "saldo_bloco_anterior"
COLUNA_SALDO_RECENTE = "saldo_bloco_recente"
COLUNAS_BLOCO = [COLUNA_SALDO_ANTERIOR, COLUNA_SALDO_RECENTE]


def anexar_blocos(agregado: pd.DataFrame) -> pd.DataFrame:
    """Anexa a cada linha o saldo da sua célula em cada bloco de 12 meses.

    Como o estoque, é atributo da célula (somado uma vez por célula em
    `agregar_metricas`), por isso a aceleração sai certa com qualquer filtro de
    período. Sem meses do bloco anterior (base de 12 meses), não anexa nada.
    """
    if not set(CHAVES_ESTOQUE) <= set(agregado.columns):
        return agregado
    mes = agregado[COLUNA_MES].astype(str)
    if not mes.between(*BLOCO_ANTERIOR).any():
        return agregado
    saldo = agregado[COLUNA_ADMISSOES] - agregado[COLUNA_DESLIGAMENTOS]
    blocos = pd.DataFrame({
        COLUNA_SALDO_ANTERIOR: saldo.where(mes.between(*BLOCO_ANTERIOR), 0),
        COLUNA_SALDO_RECENTE: saldo.where(mes.between(*BLOCO_RECENTE), 0),
    })
    chave = [agregado[c] for c in CHAVES_ESTOQUE]
    por_celula = blocos.groupby(chave, dropna=False).transform("sum")
    return agregado.assign(**{c: por_celula[c] for c in COLUNAS_BLOCO})


def periodo_padrao(meses: list[str]) -> tuple[str, str]:
    """O painel abre nos últimos 12 meses (o bloco recente, como a base fornecida)."""
    return meses[max(0, len(meses) - 12)], meses[-1]


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

    escopo: str = ESCOPO_PADRAO
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


def filtrar_cbo(ctx: "Contexto") -> pd.DataFrame | None:
    """A tabela por CBO no recorte atual (escopo, período, setor, macrofamília, nível).

    A tabela não tem município: um filtro de micro/município usa as
    mesorregiões que o contêm (como o perfil).
    """
    tabela = ctx.art.cbo
    if tabela is None or tabela.empty:
        return None
    f = ctx.filtros
    tabela = tabela[mascara_escopo(tabela, f.escopo)]
    if f.meses:
        meses = tabela[COLUNA_MES].astype(str)
        tabela = tabela[(meses >= f.meses[0]) & (meses <= f.meses[1])]
    regioes = sorted(ctx.df[COLUNA_REGIAO].astype(str).unique()) if f.territorios else []
    return aplicar_filtros(tabela, regiao=regioes, **{COLUNA_SETOR: f.setores, COLUNA_MACROFAMILIA_CBO: f.macrofamilias,
                                                      COLUNA_NIVEL_QUALIFICACAO: f.niveis})


def mascara_escopo(df: pd.DataFrame, escopo: str) -> pd.Series:
    """Linhas do escopo (agregado, perfil ou estoque): C, B–F ou toda a economia (NAR-03)."""
    if escopo == ESCOPO_TRANSFORMACAO and COLUNA_SECAO_INDUSTRIAL in df.columns:
        return df[COLUNA_SECAO_INDUSTRIAL].astype(str) == SECAO_TRANSFORMACAO
    if escopo in (ESCOPO_TRANSFORMACAO, ESCOPO_INDUSTRIA) and COLUNA_ESCOPO_INDUSTRIAL in df.columns:
        return df[COLUNA_ESCOPO_INDUSTRIAL].astype(bool)
    return pd.Series(True, index=df.index)


def fracao_secao(df: pd.DataFrame, por: list[str], secao: str) -> pd.Series:
    """Fração das movimentações de cada grupo que está na seção CNAE `secao` (rótulo)."""
    if COLUNA_SECAO_INDUSTRIAL not in df.columns or df.empty:
        return pd.Series(dtype="float64")
    mov = df[COLUNA_ADMISSOES] + df[COLUNA_DESLIGAMENTOS]
    na_secao = mov.where(df[COLUNA_SECAO_INDUSTRIAL].astype(str) == secao, 0)
    chave = [df[c] for c in por]
    soma = mov.groupby(chave, observed=True).sum()
    return (na_secao.groupby(chave, observed=True).sum() / soma.where(soma > 0)).fillna(0.0)


def marcar_secao(m: pd.DataFrame, df: pd.DataFrame, por: list[str], secao: str,
                 fracao_minima: float = FRACAO_CONSTRUCAO) -> pd.Series:
    """Booleano por linha de `m`: ≥ `fracao_minima` das movimentações do grupo estão em `secao`."""
    if m.empty:
        return pd.Series(dtype=bool)
    fracao = fracao_secao(df, por, secao)
    chaves = list(zip(*(m[c] for c in por))) if len(por) > 1 else list(m[por[0]])
    return pd.Series([float(fracao.get(k, 0.0)) >= fracao_minima for k in chaves], index=m.index, dtype=bool)


def filtrar(df: pd.DataFrame, filtros: Filtros, *, ignorar: tuple[str, ...] = ()) -> pd.DataFrame:
    """Aplica os filtros globais; ``ignorar`` pula dimensões (ex.: território)."""
    if df is None or df.empty:
        return df
    selecoes: dict[str, object] = {}
    df = df[mascara_escopo(df, filtros.escopo)]
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
M_ESTOQUE = "estoque"
M_ROT_DESC = "rotatividade_desc"
M_VAR_REL = "variacao_rel"
M_PRECOCE = "precoce"
M_ACEL = "aceleracao"
M_AMOSTRA_OK = "amostra_ok"
M_SALARIO_OK = "salario_ok"
M_TAXA_ADM = "taxa_admissao"   # ANA-03: proxy de demanda


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
    M_ESTOQUE: Definicao("Estoque de vínculos", "vínculos CLT ativos em 31/12/2025 (RAIS)", "int"),
    M_ROT_DESC: Definicao(
        "Rotatividade descontada",
        "min(admissões, desligamentos descontados) ÷ estoque em 31/12/2025 (RAIS). Descontados = sem a "
        "pedido, aposentadoria, morte e transferência (definição do MTE). O estoque de 31/12 aproxima o "
        "estoque médio; com menos de 12 meses no filtro, a taxa cobre só o período.",
        "pct",
    ),
    M_VAR_REL: Definicao("Variação do emprego", "saldo ÷ estoque em 31/12/2025 (RAIS)", "pct"),
    M_TAXA_ADM: Definicao(
        "Taxa de admissão",
        "admissões ÷ estoque em 31/12/2025 (RAIS): quantas contratações para cada 100 empregos existentes. "
        "É o proxy de demanda: com menos de 12 meses no filtro, a taxa cobre só o período.",
        "pct",
    ),
    M_ACEL: Definicao(
        "Aceleração",
        "(saldo set/25–ago/26 − saldo set/24–ago/25) ÷ estoque em 31/12/2025: quanto o emprego cresceu a "
        "mais (ou a menos) que no ano anterior. Compara blocos de 12 meses, sem efeito de calendário; "
        "não depende do filtro de período.",
        "pp",
    ),
    M_PRECOCE: Definicao(
        "Desligamento precoce",
        "desligados com menos de 12 meses de casa ÷ desligados em 2025 (RAIS, sem transferências)",
        "pct",
    ),
    M_SAL_ADM: Definicao("Salário médio de admissão", "soma dos salários ÷ admissões com salário", "brl"),
    M_SAL_DESL: Definicao("Salário médio de desligamento", "soma dos salários ÷ desligamentos com salário", "brl"),
    M_ESC_ADM: Definicao("Escolaridade média de quem entra",
                         "nível ordinal médio dos admitidos (1 = analfabeto … 11 = doutorado)", "num2"),
    COLUNA_IDHM_2010: Definicao("IDHM 2010", "Índice de Desenvolvimento Humano Municipal (PNUD, 2010)", "num2"),
    COLUNA_PIB_PER_CAPITA_2023: Definicao("PIB per capita 2023", "PIB municipal ÷ população (IBGE, 2023)", "brl"),
}


# NAR-04: uma frase simples por indicador (tooltip). A fórmula vem depois, para quem quiser.
EXPLICACAO: dict[str, str] = {
    M_MOV: "Quantas contratações e desligamentos houve no período.",
    M_SALDO: "Quantas vagas foram criadas (positivo) ou fechadas (negativo).",
    M_SALDO_10K: "Saldo de vagas proporcional à população: compara territórios de tamanhos diferentes.",
    M_SAIDA_VOL: "De cada 100 desligamentos, quantos foram pedido do próprio trabalhador.",
    M_GAP_SAL: "Quanto quem é contratado ganha em relação a quem saiu.",
    M_GAP_ESC: "Se quem entra estudou mais (positivo) ou menos (negativo) do que quem sai.",
    M_SALDO_REL: "Quanto do movimento virou vaga nova.",
    M_ESTOQUE: "Quantos empregos formais existiam em 31/12/2025.",
    M_ROT_DESC: "Quanto da equipe foi trocada no período, sem contar quem pediu para sair, se aposentou ou morreu.",
    M_VAR_REL: "Quanto o emprego cresceu ou encolheu, em % dos empregos existentes.",
    M_TAXA_ADM: "Quantas contratações houve para cada 100 empregos existentes: mede a demanda por gente.",
    M_ACEL: "Se o emprego está crescendo mais rápido (ou mais devagar) do que no ano anterior.",
    M_PRECOCE: "De cada 100 desligados, quantos saíram antes de completar 1 ano na empresa.",
    M_SAL_ADM: "Salário médio de quem foi contratado.",
    M_SAL_DESL: "Salário médio de quem saiu.",
    M_ESC_ADM: "Escolaridade média de quem foi contratado.",
    COLUNA_IDHM_2010: "Índice de desenvolvimento humano do município (0 a 1).",
    COLUNA_PIB_PER_CAPITA_2023: "Riqueza produzida no município por habitante.",
}


def ajuda(nome: str) -> str:
    """Tooltip de um indicador: a frase simples e, depois, o cálculo."""
    definicao = DEFINICOES.get(nome)
    frase = EXPLICACAO.get(nome, "")
    return f"{frase} Cálculo: {definicao.formula}." if definicao else frase


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

    # Estoque e saldos por bloco: uma vez por célula distinta do grupo (nunca
    # por linha mensal).
    da_celula = [c for c in (*COLUNAS_ESTOQUE, *COLUNAS_BLOCO) if c in base.columns]
    if da_celula and set(CHAVES_ESTOQUE) <= set(base.columns):
        celulas = base.drop_duplicates([*chave, *CHAVES_ESTOQUE])
        estoque = (
            celulas.groupby(chave, observed=True, dropna=False)[da_celula]
            .sum(min_count=1)
            .reindex(somas.index)
        )
        somas = somas.join(estoque)

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
    sem = pd.Series(float("nan"), index=r.index)
    r[M_ESTOQUE] = r["estoque_31dez"].astype("float64") if "estoque_31dez" in r else sem
    desl_desc = r[COLUNA_DESLIGAMENTOS_DESCONTADOS].astype("float64")
    r[M_ROT_DESC] = _divisao(pd.concat([adm, desl_desc], axis=1).min(axis=1), r[M_ESTOQUE])
    r[M_VAR_REL] = _divisao(r[M_SALDO], r[M_ESTOQUE])
    r[M_TAXA_ADM] = _divisao(adm, r[M_ESTOQUE])
    r[M_ACEL] = (
        _divisao(r[COLUNA_SALDO_RECENTE] - r[COLUNA_SALDO_ANTERIOR], r[M_ESTOQUE]) * 100  # p.p.
        if COLUNA_SALDO_RECENTE in r else sem
    )
    r[M_PRECOCE] = (_divisao(r["desligados_precoce"], r["desligados_rais"])
                    if "desligados_rais" in r else sem)
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

# Rótulos dos quadrantes e a função `quadrante` moram em `dashboard.regras` (NAR-01).

# Tensão = só sintomas, com pesos iguais (M4.C6). A compressão salarial é causa
# (ver `causas`), não sintoma. Sem o estoque da RAIS, os dois sintomas dela ficam
# ausentes e a média usa só a saída voluntária.
PESOS_TENSAO_PADRAO = {M_ROT_DESC: 1.0, M_SAIDA_VOL: 1.0, M_PRECOCE: 1.0}
# Dinamismo = variação do emprego (saldo ÷ estoque); sem estoque, saldo relativo.
# A aceleração por blocos de 12 meses volta no M5.C6.
PESOS_DINAMISMO_PADRAO = {M_VAR_REL: 1.0, M_ACEL: 1.0}

ROTULO_COMPONENTE = {
    M_ROT_DESC: "rotatividade alta",
    M_SAIDA_VOL: "saída voluntária alta",
    M_PRECOCE: "desligamento precoce alto",
    M_VAR_REL: "variação do emprego",
    M_ACEL: "aceleração",
}

# Rotatividade descontada oficial, out/25–set/26 (MTE; PLANEJAMENTO §6).
ROTATIVIDADE_OFICIAL = {"SC": 0.336, "Brasil": 0.342, "Transformação (Brasil)": 0.276}


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
    variacao = m[M_VAR_REL] if m[M_VAR_REL].notna().any() else m[M_SALDO_REL]
    comp = pd.DataFrame(
        {
            M_ROT_DESC: zscore(m[M_ROT_DESC]),
            M_SAIDA_VOL: zscore(m[M_SAIDA_VOL]),
            M_PRECOCE: zscore(m[M_PRECOCE]),
            M_VAR_REL: zscore(variacao),
            M_ACEL: zscore(m[M_ACEL]),
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




def causas(linha: pd.Series, *, saida_ref: float, gap_ref: float, fracao_tecnica: float = 0.0) -> list[str]:
    """Selos de causa de uma unidade, a partir das métricas e da referência do estado.

    `saida_ref` e `gap_ref` são a saída voluntária e a razão salarial entrada/saída
    do estado inteiro no mesmo escopo e período (`Contexto.ref`).

    - Salarial: razão entrada/saída ≥ 3 p.p. abaixo da do estado (ANA-01).
    - Qualificação: gap de escolaridade ≤ −0,10 numa unidade em que Técnico +
      Superior somam ao menos metade das movimentações.
    - Retenção: saída voluntária ≥ referência + 5 p.p. com salário de entrada
      não pior que o do estado (o salário não explica a saída).
    """
    selos = []
    gap = linha.get(M_GAP_SAL)
    if pd.notna(gap) and salario_pior_que_estado(gap, gap_ref):
        selos.append(CAUSA_SALARIAL)
    gap_esc = linha.get(M_GAP_ESC)
    if pd.notna(gap_esc) and gap_esc <= LIMIAR_GAP_ESCOLARIDADE and fracao_tecnica >= 0.5:
        selos.append(CAUSA_QUALIFICACAO)
    saida = linha.get(M_SAIDA_VOL)
    if pd.notna(saida) and saida >= saida_ref + MARGEM_SAIDA_VOLUNTARIA and salario_nao_explica(gap, gap_ref):
        selos.append(CAUSA_RETENCAO)
    return selos


# TAX-02: colunas que `concentracao_saldo` acrescenta a cada grupo.
COLUNAS_CONCENTRACAO = ["fracao_mes", "mes_pico", "n_meses", "fracao_municipio", "municipio_pico",
                        "n_municipios", "concentrada"]


def _pico(df: pd.DataFrame, saldo: pd.Series, por: list[str], dimensao: str) -> pd.DataFrame:
    """Por grupo: a unidade de `dimensao` com o maior saldo, a fração dela no saldo positivo e quantas há."""
    t = pd.DataFrame({**{c: df[c].astype(str) for c in por}, "d": df[dimensao].astype(str), "s": saldo})
    t = t.groupby([*por, "d"], sort=False)["s"].sum().reset_index()
    t["positivo"] = t["s"].clip(lower=0)
    t = t.sort_values("s", ascending=False, kind="stable")
    r = t.groupby(por, sort=False).agg(pico=("d", "first"), maximo=("s", "first"),
                                       soma_positiva=("positivo", "sum"), n=("d", "size"))
    r["fracao"] = r["maximo"] / r["soma_positiva"].where(r["soma_positiva"] > 0)
    return r


def concentracao_saldo(df: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """TAX-02: quanto do saldo positivo de cada grupo vem de um único mês e de um único município.

    Índice = as chaves de `por` (como texto). `concentrada` aplica a regra de
    `regras.expansao_concentrada` (limiares lá).
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=[*por, *COLUNAS_CONCENTRACAO]).set_index(por)
    saldo = (df[COLUNA_ADMISSOES] - df[COLUNA_DESLIGAMENTOS]).astype("float64")
    mes = _pico(df, saldo, por, COLUNA_MES)
    mun = _pico(df, saldo, por, COLUNA_NOME_MUNICIPIO)
    total = pd.DataFrame({c: df[c].astype(str) for c in por}).assign(s=saldo).groupby(por, sort=False)["s"].sum()
    r = pd.DataFrame({
        "fracao_mes": mes["fracao"], "mes_pico": mes["pico"], "n_meses": mes["n"],
        "fracao_municipio": mun["fracao"], "municipio_pico": mun["pico"], "n_municipios": mun["n"],
    })
    r["concentrada"] = [expansao_concentrada(float(total.get(k, 0.0)), fm, int(nm), fu, int(nu))
                        for k, fm, nm, fu, nu in zip(r.index, r["fracao_mes"], r["n_meses"],
                                                     r["fracao_municipio"], r["n_municipios"])]
    return r


def anexar_concentracao(m: pd.DataFrame, df: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """A matriz `m` com as colunas de `concentracao_saldo` (grupos sem dado: não concentrado)."""
    resultado = m.copy()
    if m.empty:
        for coluna in COLUNAS_CONCENTRACAO:
            resultado[coluna] = pd.Series(dtype="object")
        return resultado
    conc = concentracao_saldo(df, por)
    chaves = pd.MultiIndex.from_arrays([m[c].astype(str) for c in por]) if len(por) > 1 else m[por[0]].astype(str)
    alinhado = conc.reindex(chaves)
    for coluna in COLUNAS_CONCENTRACAO:
        resultado[coluna] = alinhado[coluna].to_numpy()
    resultado["concentrada"] = resultado["concentrada"].fillna(False).astype(bool)
    return resultado


def fracao_nivel_por_movimento(df: pd.DataFrame, por: list[str],
                               niveis: tuple[str, ...]) -> tuple[pd.Series, pd.Series]:
    """(fração das admissões, fração dos desligamentos) de cada grupo que está nos `niveis`."""
    no_nivel = df[COLUNA_NIVEL_QUALIFICACAO].astype(str).isin(niveis)
    chave = [df[c] for c in por]
    saida = []
    for coluna in (COLUNA_ADMISSOES, COLUNA_DESLIGAMENTOS):
        soma = df[coluna].groupby(chave, observed=True).sum()
        parte = df[coluna].where(no_nivel, 0).groupby(chave, observed=True).sum()
        saida.append(parte / soma.where(soma > 0))
    return saida[0], saida[1]


def cbos_principais(cbos: pd.DataFrame | None, regiao: str, macro: str,
                    descricoes: dict[str, str] | None = None, n: int = N_CBOS_FORMACAO) -> list[tuple[str, str, int]]:
    """As `n` CBOs com mais movimentações do grupo: (código, descrição, movimentações)."""
    if cbos is None or cbos.empty:
        return []
    sub = cbos[(cbos[COLUNA_REGIAO].astype(str) == regiao) & (cbos[COLUNA_MACROFAMILIA_CBO].astype(str) == macro)]
    if sub.empty:
        return []
    codigos = sub["cbo"].astype(str).str.strip().str.zfill(6)
    mov = (sub[COLUNA_ADMISSOES] + sub[COLUNA_DESLIGAMENTOS]).groupby(codigos).sum()
    mov = mov[mov > 0].sort_values(ascending=False).head(n)
    descricoes = descricoes or {}
    return [(cod, descricoes.get(cod, "ocupação sem descrição"), int(v)) for cod, v in mov.items()]


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
    quem_age: str = ""      # REC-02
    horizonte: str = ""
    kpi: str = ""           # "saída voluntária do grupo 59,0% → 53,0% em 12 meses (estado: 47,0%)"


def _kpi_escolhido(alavanca: str, grupo: pd.Series, ref: pd.Series):
    """(métrica, menor_melhor, valor, estado, pior?) do KPI da alavanca para o grupo, ou None.

    Entre os candidatos, usa o que está mais longe do estado, para pior
    (distância relativa); se nenhum está pior, o primeiro.
    """
    def _dados(cands):
        return [(n, menor, grupo.get(n), ref.get(n)) for n, menor in cands
                if not _vazio(grupo.get(n)) and not _vazio(ref.get(n))]

    candidatos = _dados(KPI_ALAVANCA.get(alavanca, KPI_RESERVA)) or _dados(KPI_RESERVA)
    if not candidatos:
        return None

    def _piora(item):
        _, menor, valor, estado = item
        diff = (valor - estado) if menor else (estado - valor)
        return diff / max(abs(estado), 0.05)

    piores = [x for x in candidatos if _piora(x) > 0]
    escolhido = max(piores, key=_piora) if piores else candidatos[0]
    return (*escolhido, bool(piores))


def meta_kpi(alavanca: str, grupo: pd.Series, ref: pd.Series) -> str:
    """KPI de acompanhamento com meta: andar `FRACAO_META_DISTANCIA` da distância até o estado.

    Se o grupo já está melhor em todos os candidatos, a meta é manter o patamar.
    """
    k = _kpi_escolhido(alavanca, grupo, ref)
    if k is None:
        return "—"
    nome, _, valor, estado, pior = k
    rotulo = DEFINICOES[nome].rotulo.lower()
    if not pior:
        return (f"{rotulo} do grupo: manter em {fmt_metrica(nome, valor)} ou melhor "
                f"(estado: {fmt_metrica(nome, estado)})")
    alvo = valor - FRACAO_META_DISTANCIA * (valor - estado)
    return (f"{rotulo} do grupo: {fmt_metrica(nome, valor)} → {fmt_metrica(nome, alvo)} em {PRAZO_META_MESES} meses "
            f"(estado: {fmt_metrica(nome, estado)})")


def evidencia_curta(alavanca: str, grupo: pd.Series, ref: pd.Series) -> str:
    """"saída voluntária 64,0% (estado: 50,9%)": o número que sustenta a recomendação, em uma linha."""
    k = _kpi_escolhido(alavanca, grupo, ref)
    if k is None:
        return ""
    nome, _, valor, estado, _ = k
    return f"{DEFINICOES[nome].rotulo.lower()} {fmt_metrica(nome, valor)} (estado: {fmt_metrica(nome, estado)})"


def top_executivo(recs: list["Recomendacao"], n: int = TOP_EXECUTIVO) -> list["Recomendacao"]:
    """REC-04: até `n` ações, uma por alavanca e de grupos (mesorregião × macrofamília) distintos.

    As severidades de alavancas diferentes têm escalas diferentes, então a
    prioridade só é comparada dentro de cada alavanca: dela sai a melhor
    recomendação cujo grupo ainda não apareceu. Entre as alavancas, vencem as
    de mais movimentações afetadas.
    """
    por_alavanca: dict[str, list[Recomendacao]] = {}
    for r in sorted(recs, key=lambda r: r.prioridade, reverse=True):
        if not eh_observacao(r.alavanca):  # REC-06: observação não entra no Top 3
            por_alavanca.setdefault(r.alavanca, []).append(r)
    ordem = sorted(por_alavanca, key=lambda a: por_alavanca[a][0].movimentacoes, reverse=True)
    escolhidas, grupos = [], set()
    for alavanca in ordem:
        livre = next((r for r in por_alavanca[alavanca] if (r.regiao, r.macrofamilia) not in grupos), None)
        if livre is not None:
            escolhidas.append(livre)
            grupos.add((livre.regiao, livre.macrofamilia))
        if len(escolhidas) == n:
            break
    return sorted(escolhidas, key=lambda r: r.movimentacoes, reverse=True)


def nome_curto_cbo(descricao: str) -> str:
    """"Salsicheiro (Fabricacao de Linguica…)" → "salsicheiro"; "Auxiliar de Escritorio, em Geral" → "auxiliar de escritorio"."""
    texto = str(descricao).split("(")[0].split(", em Geral")[0].strip()
    if len(texto) > 30 and " e " in texto:  # "Trabalhador de Tratamento do Leite e Fabricacao…" → antes do " e "
        texto = texto.split(" e ")[0]
    return texto if texto.isupper() else texto.lower()


def gerar_recomendacoes(
    df: pd.DataFrame,
    *,
    mediana_regional: dict[tuple[str, str], float] | None = None,
    ref: pd.Series | None = None,
    cbos: pd.DataFrame | None = None,
    descricoes: dict[str, str] | None = None,
) -> list[Recomendacao]:
    """Avalia as 5 regras por mesorregião × macrofamília (com guarda de amostra).

    As referências ("alta", "pior") vêm de `ref`: o estado inteiro no mesmo
    escopo e período (`Contexto.ref`). Sem `ref`, usa o total de `df`. Assim o
    critério se explica sozinho: "saída voluntária 58% vs 47% no estado".
    """
    if df is None or df.empty:
        return []
    mediana_regional = mediana_regional or {}
    ref = total(df) if ref is None else ref
    saida_ref, gap_ref = ref[M_SAIDA_VOL], ref[M_GAP_SAL]
    por = [COLUNA_REGIAO, COLUNA_MACROFAMILIA_CBO]
    m = matriz_diagnostico(df, por)
    if m.empty:
        return []
    frac_basico = fracao_por_nivel(df, por, ("Básico",))
    tec_adm, tec_desl = fracao_nivel_por_movimento(df, por, NIVEIS_QUALIFICADOS)
    precoce_ref = ref[M_PRECOCE] if M_PRECOCE in ref else float("nan")
    nivel_dominante = _nivel_dominante(df, por)

    # REC-03: origens possíveis da atração de talentos = mesorregião × macrofamília
    # × nível com amostra, saldo < 0 e saída voluntária abaixo da do estado.
    por_nivel = agregar_metricas(df, por + [COLUNA_NIVEL_QUALIFICACAO])
    origens = por_nivel[por_nivel[M_AMOSTRA_OK] & (por_nivel[M_SALDO] < 0)
                        & (por_nivel[M_SAIDA_VOL] < saida_ref)]
    recs: list[Recomendacao] = []
    for _, u in m.iterrows():
        chave = (u[COLUNA_REGIAO], u[COLUNA_MACROFAMILIA_CBO])
        regiao, macro = str(chave[0]), str(chave[1])
        nivel = nivel_dominante.get(chave, "—")
        mov = float(u[M_MOV])
        saida, gap = u[M_SAIDA_VOL], u[M_GAP_SAL]

        def add(alavanca, regra, evidencia, severidade, alvo=nivel, **extras):
            extras.setdefault("acao", ACAO_ALAVANCA.get(alavanca, "").format(macro=macro, regiao=regiao))
            extras.setdefault("destaque", evidencia_curta(alavanca, u, ref))
            recs.append(Recomendacao(regiao, macro, alavanca, regra, evidencia, alvo,
                                     float(severidade), mov, extras=extras,
                                     quem_age=QUEM_AGE.get(alavanca, "—"), horizonte=HORIZONTE.get(alavanca, "—"),
                                     kpi=meta_kpi(alavanca, u, ref)))

        if salario_pior_que_estado(gap, gap_ref) and pd.notna(saida) and saida >= saida_ref + MARGEM_SAIDA_VOLUNTARIA:
            ref_sal = mediana_regional.get(chave)
            texto_ref = f"; mediana regional de admissão {fmt_brl(ref_sal)}" if ref_sal else ""
            add(ALAVANCA_SALARIO,
                f"razão salarial entrada/saída ≥ {fmt_num(MARGEM_SALARIAL_RELATIVA * 100, 0)} p.p. pior que a do estado "
                f"e saída voluntária ≥ estado + {fmt_num(MARGEM_SAIDA_VOLUNTARIA * 100, 0)} p.p.",
                f"quem entra ganha {fmt_pct(gap, 0)} do salário de quem saiu (estado: {fmt_pct(gap_ref, 0)}); "
                f"saída voluntária {fmt_pct(saida)} vs {fmt_pct(saida_ref)} no estado{texto_ref}",
                (gap_ref - gap) + (saida - saida_ref))
        # REC-01: formação profissional direcionada (regra em `regras.py`).
        if (u["quadrante"] in QUADRANTES_FORMACAO and nivel in NIVEIS_ALVO_FORMACAO
                and macro not in MACROFAMILIAS_FORA_FORMACAO):
            sinais, peso = [], 0.0
            gap_esc = u[M_GAP_ESC]
            if pd.notna(gap_esc) and gap_esc < LIMIAR_FORMACAO_GAP_ESC:
                sinais.append(f"entra gente menos escolarizada (gap {fmt_num(gap_esc, 2)} nível)")
                peso += -gap_esc
            precoce = u.get(M_PRECOCE)
            if pd.notna(precoce) and pd.notna(precoce_ref) and precoce > precoce_ref:
                sinais.append(f"desligamento precoce {fmt_pct(precoce)} vs {fmt_pct(precoce_ref)} no estado")
                peso += precoce - precoce_ref
            ta, td = tec_adm.get(chave, float("nan")), tec_desl.get(chave, float("nan"))
            if pd.notna(ta) and pd.notna(td) and td - ta >= MARGEM_FORMACAO_TECNICO:
                sinais.append(f"Técnico + Superior são {fmt_pct(ta)} dos admitidos e {fmt_pct(td)} dos desligados")
                peso += td - ta
            if sinais:
                lista = cbos_principais(cbos, regiao, macro, descricoes)
                ocupacoes = ", ".join(f"{d} ({cod})" for cod, d, _ in lista) or "as ocupações de maior volume do grupo"
                add(ALAVANCA_FORMACAO,
                    REGRA_ALAVANCA[ALAVANCA_FORMACAO],
                    f"{u['quadrante']}; " + "; ".join(sinais),
                    peso, acao=f"Turmas de qualificação/aprendizagem industrial para {ocupacoes} na mesorregião {regiao}",
                    cbos=lista)
        if u["quadrante"] == Q_APAGAO and u[M_SALDO] > 0:
            cand = origens[(origens[COLUNA_MACROFAMILIA_CBO].astype(str) == macro)
                           & (origens[COLUNA_NIVEL_QUALIFICACAO].astype(str) == str(nivel))
                           & (origens[COLUNA_REGIAO].astype(str) != regiao)]
            if not cand.empty:
                o = cand.sort_values(M_SALDO).iloc[0]
                origem = str(o[COLUNA_REGIAO])
                add(ALAVANCA_MOBILIDADE, REGRA_ALAVANCA[ALAVANCA_MOBILIDADE],
                    f"{origem} → {regiao} ({macro}, nível {nivel}): lá, saldo {fmt_int(o[M_SALDO])} com saída voluntária "
                    f"{fmt_pct(o[M_SAIDA_VOL])} (estado: {fmt_pct(saida_ref)}); aqui, saldo {fmt_int(u[M_SALDO])} "
                    f"em {Q_APAGAO}",
                    float(u[M_SALDO_REL]), origem=origem,
                    acao=f"Atrair profissionais de {macro.lower()} (nível {nivel}) de {origem} para {regiao}")
        f_bas = float(frac_basico.get(chave, 0.0))
        # Sem a taxa de reposição (função exata do saldo relativo, M1.C2), a
        # regra fica com o que ela media: mão de obra básica sem expansão.
        if f_bas >= 0.5 and u[M_SALDO] <= 0:
            add(ALAVANCA_AUTOMACAO,
                "nível Básico ≥ 50% e saldo ≤ 0",
                f"{fmt_pct(f_bas)} em nível Básico; saldo {fmt_int(u[M_SALDO])}",
                f_bas - 0.5, alvo="Básico")
        if pd.notna(saida) and saida >= saida_ref + MARGEM_SAIDA_VOLUNTARIA and salario_nao_explica(gap, gap_ref):
            add(ALAVANCA_RETENCAO,
                f"saída voluntária ≥ estado + {fmt_num(MARGEM_SAIDA_VOLUNTARIA * 100, 0)} p.p. com salário de entrada "
                "não pior que o do estado (o salário não explica)",
                f"saída voluntária {fmt_pct(saida)} vs {fmt_pct(saida_ref)}; quem entra ganha {fmt_pct(gap, 0)} do "
                f"salário de quem saiu (estado: {fmt_pct(gap_ref, 0)})",
                saida - saida_ref)
    for r in recs:
        r.prioridade = r.severidade * r.movimentacoes
    return sorted(recs, key=lambda r: r.prioridade, reverse=True)


def custo_reposicao(t: pd.Series, salarios: float) -> float:
    """REC-05: desligamentos a pedido × salário médio de desligamento × `salarios` (custo de repor cada um)."""
    return float(t[COLUNA_DESLIGAMENTOS_A_PEDIDO]) * float(t[M_SAL_DESL]) * float(salarios)


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


COLUNAS_ESCOLARIDADE_CONTRATACAO = [
    "admissoes", "desligamentos", "medio_adm", "medio_desl", "superior_adm", "superior_desl",
    "mediana_medio", "n_medio", "mediana_superior", "n_superior", "premio"]


def escolaridade_contratacao(perfil: pd.DataFrame | None, por: list[str] | None = None) -> pd.DataFrame:
    """ANA-02: o mercado contrata mais instruídos e paga mais por isso?

    Por grupo (`por`; vazio = uma linha com o total): a fração de admitidos e de
    desligados com médio completo ou mais e com superior completo, e o prêmio do
    diploma = mediana de admissão com superior completo ÷ com médio completo
    (só com ≥ `MIN_SALARIOS` salários de cada faixa; senão NaN).
    """
    por = list(por or [])
    if perfil is None or perfil.empty:
        return pd.DataFrame(columns=[*por, *COLUNAS_ESCOLARIDADE_CONTRATACAO])
    base = perfil.assign(_todos="") if not por else perfil
    chave = por or ["_todos"]
    faixa = base[COLUNA_FAIXA_ESCOLARIDADE].astype(str)
    medio, superior = faixa.isin(FAIXAS_MEDIO_OU_MAIS), faixa == FAIXA_SUPERIOR
    contagens = pd.DataFrame({
        **{k: base[k].astype(str) for k in chave},
        "admissoes": base[COLUNA_ADMISSOES], "desligamentos": base[COLUNA_DESLIGAMENTOS],
        "medio_adm": base[COLUNA_ADMISSOES].where(medio, 0), "medio_desl": base[COLUNA_DESLIGAMENTOS].where(medio, 0),
        "superior_adm": base[COLUNA_ADMISSOES].where(superior, 0),
        "superior_desl": base[COLUNA_DESLIGAMENTOS].where(superior, 0),
    }).groupby(chave, sort=False).sum()
    for lado in ("adm", "desl"):
        total_lado = contagens["admissoes" if lado == "adm" else "desligamentos"]
        for nome in ("medio", "superior"):
            contagens[f"{nome}_{lado}"] = contagens[f"{nome}_{lado}"] / total_lado.where(total_lado > 0)
    faixas = base[faixa.isin([FAIXA_MEDIO, FAIXA_SUPERIOR])].copy()
    for k in chave:
        faixas[k] = faixas[k].astype(str)
    med = medianas_perfil(faixas, [*chave, COLUNA_FAIXA_ESCOLARIDADE]) if not faixas.empty else pd.DataFrame(
        columns=[*chave, COLUNA_FAIXA_ESCOLARIDADE, "mediana_admissao", "n_admissao"])
    for nome, rotulo in (("medio", FAIXA_MEDIO), ("superior", FAIXA_SUPERIOR)):
        m = med[med[COLUNA_FAIXA_ESCOLARIDADE].astype(str) == rotulo].set_index(chave)
        contagens[f"mediana_{nome}"] = m["mediana_admissao"].reindex(contagens.index).astype("float64")
        contagens[f"n_{nome}"] = m["n_admissao"].reindex(contagens.index).fillna(0).astype("int64")
    ok = (contagens["n_medio"] >= MIN_SALARIOS) & (contagens["n_superior"] >= MIN_SALARIOS)
    contagens["premio"] = (contagens["mediana_superior"] / contagens["mediana_medio"]).where(ok)
    resultado = contagens.reset_index()
    return resultado.drop(columns="_todos") if not por else resultado


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


# BUG-04: escala monetária única do painel (mil / mi / bi, uma casa decimal).
_ESCALAS_BRL = [(1e9, "bi"), (1e6, "mi"), (1e3, "mil")]


def fmt_brl_escala(valor) -> str:
    """Valor monetário grande em escala pt-BR: 2_174_600_000 → "R$ 2,2 bi".

    Usa a maior escala em que o valor arredondado fica ≥ 1 (nunca "2.174,6 mi");
    abaixo de mil, cai em `fmt_brl`. NaN → "—".
    """
    if _vazio(valor):
        return "—"
    v = float(valor)
    sinal = "−" if v < 0 else ""
    for base, sufixo in _ESCALAS_BRL:
        if round(abs(v) / base, 1) >= 1:
            # Arredondar 999,96 mi para "1.000,0 mi" vira a escala de cima.
            if sufixo != "bi" and round(abs(v) / base, 1) >= 1000:
                continue
            return f"{sinal}R$ {fmt_num(abs(v) / base, 1)} {sufixo}"
    return f"{sinal}R$ {fmt_num(abs(v), 0)}"


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


def carregar_meta_rodada2() -> dict:
    """Procedência da classificação usada como 2ª rodada (auditoria)."""
    try:
        return json.loads(CAMINHO_META_RODADA2.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def descricoes_cbo(mapa: pd.DataFrame | None = None) -> dict[str, str]:
    """Código CBO com 6 dígitos (zeros à esquerda) → descrição oficial."""
    if mapa is None:
        mapa = carregar_cbo()[0]
    if mapa is None or mapa.empty or "descricao" not in mapa:
        return {}
    codigos = mapa["cbo2002ocupação"].astype(str).str.strip().str.zfill(6)
    return dict(zip(codigos, mapa["descricao"].astype(str)))



# TAX-05: o que a IA acrescentou à hierarquia da CBO.
DECISAO_SEGUIU = "seguiu o prefixo"
DECISAO_CONTRARIOU = "contrariou o prefixo"
DECISAO_SEM_PREFIXO = "prefixo não sugere família"


def decisoes_ia(mapa: pd.DataFrame | None, cbos: pd.DataFrame | None) -> pd.DataFrame:
    """Cada CBO com movimentação no recorte, a família da IA × a sugerida pelo prefixo e o nível × o do grande grupo.

    `mapa` = `cbo_macrofamilias.csv` (a saída da IA); `cbos` = a tabela por CBO
    do recorte (`filtrar_cbo`). `decisao` diz se a IA seguiu ou contrariou o
    prefixo da tabela de desempate, ou se o prefixo não sugere família.
    """
    from src.cbo_ia import familia_sugerida, nivel_cbo

    colunas = ["cbo", "descricao", "macrofamilia", "familia_prefixo", "nivel", "nivel_grande_grupo",
               "justificativa", "movimentacoes", "decisao", "nivel_ajustado"]
    if mapa is None or mapa.empty or cbos is None or cbos.empty:
        return pd.DataFrame(columns=colunas)
    codigos = cbos["cbo"].astype(str).str.strip().str.zfill(6)
    mov = (cbos[COLUNA_ADMISSOES] + cbos[COLUNA_DESLIGAMENTOS]).groupby(codigos).sum()
    d = pd.DataFrame({
        "cbo": mapa["cbo2002ocupação"].astype(str).str.strip().str.zfill(6),
        "descricao": mapa["descricao"].astype(str),
        "macrofamilia": mapa["macrofamilia"].astype(str),
        "nivel": mapa["nivel_qualificacao"].astype(str),
        "justificativa": mapa["justificativa"].fillna("").astype(str) if "justificativa" in mapa else "",
    })
    d["movimentacoes"] = d["cbo"].map(mov).fillna(0)
    d = d[d["movimentacoes"] > 0].copy()
    d["familia_prefixo"] = d["cbo"].map(familia_sugerida)
    d["nivel_grande_grupo"] = d["cbo"].map(nivel_cbo)
    d["decisao"] = [DECISAO_SEM_PREFIXO if pd.isna(p) else DECISAO_SEGUIU if f == p else DECISAO_CONTRARIOU
                    for f, p in zip(d["macrofamilia"], d["familia_prefixo"])]
    d["nivel_ajustado"] = d["nivel"] != d["nivel_grande_grupo"]
    return d[colunas].sort_values("movimentacoes", ascending=False).reset_index(drop=True)


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


def descricoes_cbo_cache() -> dict[str, str]:
    return descricoes_cbo(cbo_cache()[0])


def _meses(df: pd.DataFrame) -> list[str]:
    return sorted(df[COLUNA_MES].astype(str).unique())


def limpar_filtros(df: pd.DataFrame | None = None) -> None:
    """Volta todos os filtros ao padrão (transformação, últimos 12 meses)."""
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
    estado.setdefault("f_escopo", ESCOPO_PADRAO)
    if estado["f_escopo"] not in ESCOPOS:
        estado["f_escopo"] = ESCOPO_PADRAO
    estado.setdefault("f_meses", periodo_padrao(meses))
    estado.setdefault("f_nivel", NIVEL_MESO)
    if tuple(estado["f_meses"])[0] not in meses or tuple(estado["f_meses"])[1] not in meses:
        estado["f_meses"] = periodo_padrao(meses)

    lateral = st.sidebar
    lateral.markdown("### Filtros")
    lateral.radio("Escopo", list(ESCOPOS), key="f_escopo", help=AJUDA_ESCOPO)
    lateral.select_slider("Período", options=meses, key="f_meses", format_func=rotulo_mes)
    lateral.radio("Nível territorial", [NIVEL_MESO, NIVEL_MICRO, NIVEL_MUNICIPIO], key="f_nivel",
                  horizontal=True, on_change=lambda: estado.update(f_terr=[]))

    escopo_df = df[mascara_escopo(df, estado["f_escopo"])]
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
    return montar_contexto(art, Filtros(meses=periodo_padrao(_meses(art.agregado))))


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

/* BUG-06: sem o link-âncora nos títulos de markdown (clicar no título mudava a URL);
   st.title/header/subheader já usam anchor=False. O ícone de ajuda (help=) continua. */
[data-testid="stMain"] [data-testid="stHeaderActionElements"] a[href^="#"] {display: none;}

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
.rx-neutro {color: var(--rx-suave);}
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
[class*="st-key-rx-alerta-retracao"] {border-left-color: #E69F00 !important;}
.rx-semaforo {display: inline-flex; align-items: center; gap: .4rem; font-weight: 700; font-size: .9rem; color: var(--rx-texto);}
.rx-semaforo::before {content: ""; width: .8rem; height: .8rem; border-radius: 50%; background: currentColor;}
.rx-semaforo.rx-apagao::before {background: #D55E00;}
.rx-semaforo.rx-retracao::before {background: #E69F00;}
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


# BUG-01: métricas absolutas (contagens) de um território não se comparam com o
# absoluto do estado inteiro por diferença ("−4.639 vs estado" não diz nada).
# Para elas o painel mostra a participação no total estadual (`participacao_estadual`);
# o delta "vs estado" fica só para taxas e razões.
METRICAS_ABSOLUTAS = {M_MOV, M_SALDO, M_ESTOQUE}
# Curto de propósito: o texto cabe no rodapé dos cartões estreitos (3 por linha).
_TOTAL_ESTADUAL = {M_MOV: "do estado", M_SALDO: "do estado", M_ESTOQUE: "do estado"}


def participacao_estadual(nome: str, valor: float, referencia: float) -> str | None:
    """"38,2% do estado" para métricas absolutas; com sinais opostos, só o valor do estado.

    Com sinais opostos (território fechou vagas, estado abriu) a fração seria
    negativa e sem leitura; mostramos o total do estado como referência.
    """
    if nome not in METRICAS_ABSOLUTAS or _vazio(valor) or _vazio(referencia) or float(referencia) == 0:
        return None
    valor, referencia = float(valor), float(referencia)
    if valor * referencia < 0:
        return f"estado: {fmt_int(referencia)}"
    return f"{fmt_pct(valor / referencia)} {_TOTAL_ESTADUAL[nome]}"


def delta_texto(nome: str, valor: float, referencia: float, sufixo: str) -> str | None:
    """Delta pt-BR de uma taxa/razão vs referência ("+2,3 p.p. vs SC").

    Métricas absolutas devolvem ``None``: use `participacao_estadual` (BUG-01).
    """
    if nome in METRICAS_ABSOLUTAS or _vazio(valor) or _vazio(referencia):
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
METRICAS_INVERSAS = {M_SAIDA_VOL, M_ROT_DESC, M_PRECOCE}


# Temas da coluna de indicadores (sanfona do Panorama): título, ícone e métricas.
TEMAS_KPI = [
    ("Movimentação", ":material/swap_horiz:", [M_MOV, M_SALDO, M_SALDO_10K, M_VAR_REL, M_ACEL, M_TAXA_ADM]),
    ("Renda", ":material/payments:", [M_GAP_SAL, M_SAL_ADM, M_SAL_DESL]),
    ("Escolaridade", ":material/school:", [M_GAP_ESC]),
    ("Perda de gente", ":material/crisis_alert:", [M_ROT_DESC, M_SAIDA_VOL, M_PRECOCE]),
]
METRICAS_TEMAS = [m for _, _, ms in TEMAS_KPI for m in ms]

# Unidade por extenso, em cinza sob/ao lado do valor.
UNIDADES = {
    M_MOV: "admissões + desligamentos",
    M_SALDO: "vagas",
    M_SALDO_10K: "vagas por 10 mil hab.",
    M_SALDO_REL: "do total movimentado",
    M_SAIDA_VOL: "dos desligamentos, a pedido",
    M_ROT_DESC: "oficial (MTE): SC 33,6% · Brasil 34,2% · Transformação 27,6%",
    M_VAR_REL: "do estoque de 31/12/2025",
    M_TAXA_ADM: "admissões por 100 empregos de 31/12/2025",
    M_ACEL: "vs o ano anterior (blocos de 12 meses)",
    M_PRECOCE: "dos desligados, com < 12 meses de casa",
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
        texto_ajuda = ajuda(nome)
        if nome == M_GAP_SAL and not atual[M_SALARIO_OK]:
            texto_ajuda += " Amostra salarial insuficiente nesta seleção."
        delta = None if ref is None else delta_texto(nome, atual[nome], ref[nome], "vs estado")
        extra = ""
        if delta:
            subiu = delta.startswith("+")
            bom = subiu != (nome in METRICAS_INVERSAS)
            extra = (f'<span class="rx-delta {"rx-bom" if bom else "rx-ruim"}">'
                     f'{"↑" if subiu else "↓"} {html.escape(delta)}</span>')
        elif ref is not None and (fatia := participacao_estadual(nome, atual[nome], ref[nome])):
            extra = f'<span class="rx-delta rx-neutro">{html.escape(fatia)}</span>'
        return (f'<div class="rx-linha" title="{html.escape(texto_ajuda)}">'
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


# BUG-05: plural dos níveis territoriais (nunca acrescentar um "s": "Mesorregiãos").
PLURAL_NIVEL = {NIVEL_MESO: "mesorregiões", NIVEL_MICRO: "microrregiões", NIVEL_MUNICIPIO: "municípios"}


def plural_nivel(nivel: str, maiuscula: bool = False) -> str:
    """"Mesorregião" → "mesorregiões" (ou "Mesorregiões" com `maiuscula`)."""
    texto = PLURAL_NIVEL.get(nivel, nivel.lower())
    return texto[0].upper() + texto[1:] if maiuscula else texto


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
    plural = plural_nivel(f.nivel_territorial)
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
