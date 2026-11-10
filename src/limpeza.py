"""Limpador do pipeline (R2): conversão de tipos, valores ausentes e domínios.

Este módulo trata os dados brutos lidos pelo Ingestor: converte valores
monetários do formato brasileiro para ponto flutuante, decodifica domínios
categóricos, trata valores ausentes e filtra o intervalo de competência.

Esta parte (tarefa 4.1) cobre a **conversão monetária** (R2.1–R2.4):

- `brl_para_float`: converte um único valor no formato brasileiro
  (vírgula como separador decimal, ex.: ``"2018,00"``) para `float` com
  precisão de 2 casas decimais; devolve ``NaN`` para valores não conversíveis
  e para o marcador de ausência ``"-"`` usado na Base_de_Municipios (R2.4).
- `limpar_moeda`: aplica `brl_para_float` às colunas monetárias de um
  DataFrame e coleta, por coluna e competência, a quantidade de valores que
  não puderam ser convertidos, para fins de log (R2.2).

A tarefa 4.3 cobre a **decodificação de domínios** (R2.5–R2.7):

- `decodificar_dominios`: substitui, nas colunas categóricas, cada código pelo
  rótulo legível definido no dicionário de domínio (R2.5); preserva o valor
  original e registra ``(coluna, código, contagem)`` para códigos sem rótulo
  (R2.6); transforma células vazias/ausentes em ``NaN`` sem interromper o
  processamento das demais linhas (R2.7).

A tarefa 4.5 cobre o **filtro de competência e a orquestração** (R2.3, R2.4,
R2.8, R2.9):

- `filtrar_competencia`: mantém apenas os registros cuja `competênciamov`
  (formato AAAAMM) esteja no intervalo inclusivo ``[202509, 202608]`` (R2.8) e
  devolve o DataFrame filtrado junto à contagem de registros excluídos (R2.9).
- `limpar`: orquestra a limpeza completa — conversão monetária do CAGED,
  decodificação de domínios e filtro de competência — e trata a
  Base_de_Municipios convertendo seus indicadores numéricos do formato
  brasileiro para ``float`` e o marcador ``"-"`` em ``NaN`` (R2.3, R2.4).
  Reúne os logs de falha/exclusão em um ``LimpezaResult``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from src.logging_pipeline import log_etapa
from src.mapeamentos import TAM_ESTAB_JAN_PONTO_MEDIO

# Marcador de ausência usado na Base_de_Municipios; deve virar NaN (R2.4).
MARCADOR_AUSENTE = "-"

# Colunas monetárias do CAGED tratadas pelo Limpador (R2.1).
COLUNAS_MOEDA_CAGED = ["salário", "valorsaláriofixo"]

# Coluna de faixa de tamanho do estabelecimento em janeiro (código de domínio).
COLUNA_TAM_ESTAB_JAN = "tamestabjan"

# Coluna derivada com o estoque base numérico, denominador do Turnover (R4.4).
COLUNA_ESTOQUE_BASE = "estoque_base"

# Coluna de grau de instrução (código de domínio) e a sua versão ordinal derivada.
COLUNA_GRAU_INSTRUCAO = "graudeinstrução"
COLUNA_ESCOLARIDADE_ORDINAL = "escolaridade_ordinal"

# Nível ordinal de escolaridade por código do dicionário (ver
# `derivar_escolaridade_ordinal`). O código 80 (Pós-Graduação completa) é alto
# no dicionário mas pertence entre Superior Completo (9) e Mestrado (10).
ESCOLARIDADE_ORDINAL: dict[int, float] = {
    1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0, 6: 6.0,
    7: 7.0, 8: 8.0, 9: 9.0, 80: 9.5, 10: 10.0, 11: 11.0,
}

# Coluna de competência do CAGED (formato AAAAMM) usada pelo filtro (R2.8).
COLUNA_COMPETENCIA = "competênciamov"

# Intervalo inclusivo de competências mantidas pelo filtro (R2.8).
COMPETENCIA_INICIO = 202509
COMPETENCIA_FIM = 202608

# Indicadores numéricos da Base_de_Municipios convertidos para float (R2.3).
# São as colunas socioeconômicas consumidas adiante pelo pipeline (R6.6): a
# população estimada de 2026 (denominador de Saldo_por_10k), o IDHM de 2010 e o
# PIB per capita de 2023. Os nomes seguem exatamente o cabeçalho do arquivo.
COLUNAS_INDICADORES_MUNICIPIOS = [
    "População estimada - pessoas [2026]",
    "IDHM <span>Índice de desenvolvimento humano municipal</span> [2010]",
    "PIB per capita - R$ [2023]",
]


@dataclass(frozen=True)
class RegistroFalhaMoeda:
    """Registro de falha de conversão monetária para log (R2.2).

    Agrupa, por coluna monetária e competência, a quantidade de valores que não
    puderam ser convertidos para ponto flutuante e foram substituídos por NaN.

    Attributes:
        coluna: nome da coluna monetária processada.
        competencia: competência (AAAAMM) à qual as falhas pertencem; ``None``
            quando o DataFrame não possui a coluna `competênciamov`.
        quantidade: número de valores não convertidos nesse grupo.
    """

    coluna: str
    competencia: object
    quantidade: int


def brl_para_float(valor: object) -> float:
    """Converte um valor no formato monetário brasileiro para `float` (R2.1).

    Aceita strings no padrão brasileiro, em que a vírgula é o separador decimal
    e o ponto é o separador de milhar (ex.: ``"2018,00"`` → ``2018.0``,
    ``"1.234,56"`` → ``1234.56``). Também aceita valores já numéricos, que são
    apenas arredondados. O resultado tem precisão de 2 casas decimais (R2.1,
    R2.3).

    Retorna ``NaN`` (R2.2, R2.4) quando o valor:

    - é nulo/ausente (``None``/``NaN``);
    - é o marcador de ausência ``"-"`` da Base_de_Municipios (R2.4);
    - é uma string vazia ou não conversível para número.

    Args:
        valor: valor a converter (string BR, número ou ausente).

    Returns:
        O número de ponto flutuante com 2 casas decimais, ou ``NaN`` se o valor
        não for conversível.
    """
    # Valores ausentes propagam como NaN.
    if valor is None:
        return math.nan
    if isinstance(valor, float) and math.isnan(valor):
        return math.nan

    # Valores já numéricos: apenas arredonda a 2 casas (R2.1).
    if isinstance(valor, bool):
        # bool é subclasse de int; não é um valor monetário válido.
        return math.nan
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)

    # A partir daqui tratamos como texto no formato brasileiro.
    texto = str(valor).strip()
    if texto == "" or texto == MARCADOR_AUSENTE:
        return math.nan

    # Converte do padrão BR (milhar '.', decimal ',') para o padrão de `float`:
    # remove os separadores de milhar e troca a vírgula decimal por ponto.
    normalizado = texto.replace(".", "").replace(",", ".")
    try:
        return round(float(normalizado), 2)
    except ValueError:
        return math.nan


def limpar_moeda(
    df: pd.DataFrame, colunas: list[str] = COLUNAS_MOEDA_CAGED
) -> tuple[pd.DataFrame, list[RegistroFalhaMoeda]]:
    """Aplica `brl_para_float` a colunas monetárias e coleta falhas (R2.1, R2.2).

    Para cada coluna monetária presente em ``colunas``, converte cada valor do
    formato brasileiro para ``float`` com 2 casas decimais. Valores não
    conversíveis (e o marcador ``"-"``) viram ``NaN`` (R2.2, R2.4). As falhas
    são agrupadas por coluna e por competência (`competênciamov`, quando a
    coluna existir), produzindo registros ``RegistroFalhaMoeda`` com a contagem
    de valores não convertidos — base para o log exigido por R2.2.

    Uma falha é contada quando o valor de origem *não era* ausente mas o
    resultado da conversão é ``NaN`` (ou seja, era inválido). Valores que já
    eram ausentes na origem não contam como falha de conversão.

    Args:
        df: DataFrame a tratar (não é modificado; uma cópia é retornada).
        colunas: nomes das colunas monetárias a converter. Colunas ausentes no
            DataFrame são ignoradas silenciosamente.

    Returns:
        Uma tupla ``(df_convertido, falhas)`` em que ``df_convertido`` é uma
        cópia do DataFrame com as colunas monetárias convertidas para ``float``
        e ``falhas`` é a lista de ``RegistroFalhaMoeda`` (uma entrada por
        combinação coluna × competência com pelo menos uma falha).
    """
    resultado = df.copy()
    falhas: list[RegistroFalhaMoeda] = []

    tem_competencia = "competênciamov" in resultado.columns

    for coluna in colunas:
        if coluna not in resultado.columns:
            continue

        original = resultado[coluna]
        convertido = original.map(brl_para_float)

        # Uma falha ocorre quando a origem não era ausente mas o resultado é NaN.
        origem_ausente = original.isna() | (
            original.astype("string").str.strip().isin(["", MARCADOR_AUSENTE])
        )
        falhou = convertido.isna() & ~origem_ausente

        resultado[coluna] = convertido

        if not falhou.any():
            continue

        if tem_competencia:
            # Agrupa a contagem de falhas por competência (R2.2).
            contagem_por_comp = (
                resultado.loc[falhou, "competênciamov"]
                .value_counts(dropna=False)
                .sort_index()
            )
            for competencia, quantidade in contagem_por_comp.items():
                falhas.append(
                    RegistroFalhaMoeda(
                        coluna=coluna,
                        competencia=competencia,
                        quantidade=int(quantidade),
                    )
                )
        else:
            falhas.append(
                RegistroFalhaMoeda(
                    coluna=coluna,
                    competencia=None,
                    quantidade=int(falhou.sum()),
                )
            )

    return resultado, falhas


@dataclass(frozen=True)
class CodigoNaoMapeado:
    """Registro de código categórico sem rótulo no dicionário (R2.6).

    Agrupa, por coluna categórica e código, a quantidade de ocorrências de um
    código que não possui rótulo correspondente no dicionário de domínio e, por
    isso, teve o valor original preservado.

    Attributes:
        coluna: nome da coluna categórica processada.
        codigo: código não mapeado (preservado no DataFrame).
        quantidade: número de ocorrências desse código não mapeado na coluna.
    """

    coluna: str
    codigo: object
    quantidade: int


def _normalizar_codigo_categorico(valor: object) -> object:
    """Normaliza um valor de célula categórica para casar com as chaves do mapa.

    Os mapas de domínio (``src/mapeamentos.py``) usam chaves inteiras para os
    domínios numéricos (ex.: ``1``) e textuais para a seção CNAE (ex.: ``"C"``).
    Os valores lidos do CAGED podem chegar como ``float`` (``1.0``), ``int`` ou
    ``str`` (``"1"``, ``" C "``), por isso normalizamos antes da consulta:

    - ``float`` inteiro (``1.0``) → ``int`` (``1``);
    - ``str`` numérica (``"1"``, ``"1.0"``) → ``int`` (``1``);
    - ``str`` não numérica → texto sem espaços ao redor (``" C "`` → ``"C"``);
    - demais tipos são devolvidos sem alteração.

    Args:
        valor: valor da célula a normalizar (não ausente).

    Returns:
        O código normalizado, pronto para consulta no mapa de domínio.
    """
    if isinstance(valor, bool):
        # bool é subclasse de int, mas não é um código categórico válido.
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str):
        texto = valor.strip()
        try:
            numero = float(texto)
        except ValueError:
            return texto
        if numero.is_integer():
            return int(numero)
        return numero
    return valor


def decodificar_dominios(
    df: pd.DataFrame, mapas: dict[str, dict]
) -> tuple[pd.DataFrame, list[CodigoNaoMapeado]]:
    """Decodifica colunas categóricas de códigos para rótulos legíveis (R2.5–R2.7).

    Para cada coluna presente tanto em ``mapas`` quanto no DataFrame, substitui
    cada código pelo rótulo correspondente definido no dicionário de domínio
    (R2.5). Códigos sem rótulo têm o valor original preservado e são
    contabilizados por coluna e código em ``CodigoNaoMapeado`` (R2.6). Células
    vazias ou ausentes viram ``NaN`` sem interromper o processamento das demais
    linhas (R2.7).

    A normalização de tipos (``1.0`` / ``"1"`` → ``1``; ``" C "`` → ``"C"``)
    garante que os valores do CAGED casem com as chaves dos mapas de domínio,
    que usam ``int`` para domínios numéricos e ``str`` para a seção CNAE.

    Args:
        df: DataFrame a tratar (não é modificado; uma cópia é retornada).
        mapas: dicionário ``{nome_coluna: {codigo: rotulo}}`` com os domínios a
            aplicar, no formato exposto por ``src/mapeamentos.py``. Colunas
            ausentes no DataFrame são ignoradas silenciosamente.

    Returns:
        Uma tupla ``(df_decodificado, nao_mapeados)`` em que ``df_decodificado``
        é uma cópia do DataFrame com as colunas categóricas decodificadas e
        ``nao_mapeados`` é a lista de ``CodigoNaoMapeado`` (uma entrada por
        combinação coluna × código sem rótulo, com a contagem de ocorrências).
    """
    resultado = df.copy()
    nao_mapeados: list[CodigoNaoMapeado] = []

    for coluna, mapa in mapas.items():
        if coluna not in resultado.columns:
            continue

        serie = resultado[coluna]

        # Contagem de códigos não mapeados por código original (R2.6).
        contagem_nao_mapeada: dict[object, int] = {}

        def _decodificar(valor: object) -> object:
            # Células vazias/ausentes → NaN sem interromper as demais (R2.7).
            if valor is None:
                return math.nan
            if isinstance(valor, float) and math.isnan(valor):
                return math.nan
            if isinstance(valor, str) and valor.strip() == "":
                return math.nan

            codigo = _normalizar_codigo_categorico(valor)
            if codigo in mapa:
                # Código conhecido → rótulo legível (R2.5).
                return mapa[codigo]

            # Código desconhecido → preserva o valor original e contabiliza (R2.6).
            contagem_nao_mapeada[codigo] = (
                contagem_nao_mapeada.get(codigo, 0) + 1
            )
            return valor

        resultado[coluna] = serie.map(_decodificar)

        for codigo, quantidade in contagem_nao_mapeada.items():
            nao_mapeados.append(
                CodigoNaoMapeado(
                    coluna=coluna,
                    codigo=codigo,
                    quantidade=int(quantidade),
                )
            )

    return resultado, nao_mapeados


def derivar_estoque_base(df: pd.DataFrame) -> pd.DataFrame:
    """Deriva o estoque base numérico a partir da faixa `tamestabjan` (R4.4).

    R2.5 manda decodificar `tamestabjan` para o rótulo legível da faixa
    (``"De 20 a 49"``) e R4.4 manda usar a mesma coluna como **denominador
    numérico** do Turnover. As duas coisas não cabem numa coluna só, e é daí que
    vinha o Turnover ausente em todos os recortes: a coluna era decodificada
    para texto e depois coagida para número, resultando em ``NaN``.

    A solução é separar as responsabilidades: esta função lê o **código cru** da
    faixa e grava o número de vínculos correspondente em ``estoque_base``
    (`COLUNA_ESTOQUE_BASE`), deixando `tamestabjan` livre para ser decodificada
    em rótulo por `decodificar_dominios`. Por isso ela é chamada **antes** da
    decodificação em `limpar`.

    Cada faixa é representada pelo seu ponto médio
    (`mapeamentos.TAM_ESTAB_JAN_PONTO_MEDIO`); as faixas sem tamanho definido
    (``Zero``, ``Inválido``, ``Ignorado``) e os códigos desconhecidos viram
    ``NaN``, de modo que o Turnover do recorte fique ausente (R4.5).

    Args:
        df: CAGED com a coluna `tamestabjan` ainda em código. Não é modificado;
            uma cópia é retornada. Se a coluna estiver ausente, a cópia volta
            inalterada (sem ``estoque_base``).

    Returns:
        Uma cópia de ``df`` com a coluna ``estoque_base`` (``float``) anexada.
    """
    resultado = df.copy()
    if COLUNA_TAM_ESTAB_JAN not in resultado.columns:
        return resultado

    def _ponto_medio(valor: object) -> float:
        codigo = _normalizar_codigo_categorico(valor)
        if isinstance(codigo, bool) or not isinstance(codigo, int):
            return math.nan
        return TAM_ESTAB_JAN_PONTO_MEDIO.get(codigo, math.nan)

    resultado[COLUNA_ESTOQUE_BASE] = (
        resultado[COLUNA_TAM_ESTAB_JAN].map(_ponto_medio).astype("float64")
    )
    return resultado


def derivar_escolaridade_ordinal(df: pd.DataFrame) -> pd.DataFrame:
    """Deriva o nível ordinal de escolaridade a partir de `graudeinstrução` (R4.7).

    Mesmo problema de `derivar_estoque_base`, mesma solução: R2.5 manda
    decodificar `graudeinstrução` para o rótulo legível, mas a leitura analítica
    de renda × escolaridade (R7.4) precisa de um valor **ordenável** para
    promediar por recorte. O rótulo não serve — ``"Médio Completo"`` não tem
    ordem —, então gravamos o nível numérico em ``escolaridade_ordinal`` a partir
    do código cru, antes da decodificação.

    Os códigos do dicionário já são ordinais de 1 (Analfabeto) a 11 (Doutorado),
    com uma exceção: 80 (``Pós-Graduação completa``) é numericamente alto mas
    pertence entre Superior Completo (9) e Mestrado (10) — mapeado para ``9.5``.
    Códigos desconhecidos viram ``NaN`` e são ignorados nas médias.

    Args:
        df: CAGED com a coluna `graudeinstrução` ainda em código. Não é
            modificado; uma cópia é retornada. Se a coluna estiver ausente, a
            cópia volta inalterada.

    Returns:
        Uma cópia de ``df`` com a coluna ``escolaridade_ordinal`` (``float``).
    """
    resultado = df.copy()
    if COLUNA_GRAU_INSTRUCAO not in resultado.columns:
        return resultado

    def _ordinal(valor: object) -> float:
        codigo = _normalizar_codigo_categorico(valor)
        if isinstance(codigo, bool) or not isinstance(codigo, int):
            return math.nan
        return ESCOLARIDADE_ORDINAL.get(codigo, math.nan)

    resultado[COLUNA_ESCOLARIDADE_ORDINAL] = (
        resultado[COLUNA_GRAU_INSTRUCAO].map(_ordinal).astype("float64")
    )
    return resultado


def _competencia_para_int(valor: object) -> object:
    """Coage uma competência AAAAMM para ``int`` para fins de comparação.

    O CAGED pode ser lido com a coluna `competênciamov` como texto (``"202509"``)
    ou como número (``202509`` / ``202509.0``). Para aplicar o filtro de
    intervalo (R2.8) normalizamos ambos os casos para ``int``.

    Args:
        valor: valor da competência (texto AAAAMM, número ou ausente).

    Returns:
        O inteiro AAAAMM correspondente, ou ``None`` quando o valor é ausente ou
        não representa uma competência numérica válida (tais registros ficam
        fora do intervalo e, portanto, são excluídos por R2.9).
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        # bool é subclasse de int, mas não é uma competência válida.
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    if isinstance(valor, int):
        return int(valor)
    if isinstance(valor, float):
        return int(valor) if valor.is_integer() else None

    texto = str(valor).strip()
    if texto == "" or texto == MARCADOR_AUSENTE:
        return None
    try:
        numero = float(texto)
    except ValueError:
        return None
    return int(numero) if numero.is_integer() else None


def filtrar_competencia(
    df: pd.DataFrame,
    inicio: int = COMPETENCIA_INICIO,
    fim: int = COMPETENCIA_FIM,
) -> tuple[pd.DataFrame, int]:
    """Mantém competências no intervalo inclusivo e conta os excluídos (R2.8, R2.9).

    Conserva apenas os registros cuja `competênciamov` (formato AAAAMM) esteja no
    intervalo fechado ``[inicio, fim]`` (R2.8). Os registros fora do intervalo —
    inclusive aqueles com competência ausente ou não numérica — são excluídos e
    contabilizados (R2.9). A competência é coagida para ``int`` antes da
    comparação, de modo que a coluna possa chegar como texto (``dtype=str`` na
    leitura) ou como número.

    Os registros mantidos e os excluídos são disjuntos e sua união é o conjunto
    original: ``len(df_filtrado) + qtde_excluidos == len(df)``.

    Args:
        df: DataFrame a filtrar (não é modificado; uma cópia é retornada).
        inicio: limite inferior inclusivo da competência (AAAAMM).
        fim: limite superior inclusivo da competência (AAAAMM).

    Returns:
        Uma tupla ``(df_filtrado, qtde_excluidos)`` em que ``df_filtrado`` é uma
        cópia do DataFrame contendo apenas as competências no intervalo e
        ``qtde_excluidos`` é o número de registros removidos pelo filtro.

    Raises:
        KeyError: se a coluna `competênciamov` não estiver presente no DataFrame.
    """
    if COLUNA_COMPETENCIA not in df.columns:
        raise KeyError(
            f"Coluna de competência '{COLUNA_COMPETENCIA}' ausente no DataFrame."
        )

    competencias = df[COLUNA_COMPETENCIA].map(_competencia_para_int)
    # Registros com competência nula/inválida ficam fora do intervalo (R2.9).
    no_intervalo = competencias.map(
        lambda c: c is not None and inicio <= c <= fim
    ).astype(bool)

    resultado = df.loc[no_intervalo].copy()
    qtde_excluidos = int((~no_intervalo).sum())
    return resultado, qtde_excluidos


def limpar_indicadores_municipios(
    df: pd.DataFrame,
    colunas: list[str] = COLUNAS_INDICADORES_MUNICIPIOS,
) -> tuple[pd.DataFrame, list[RegistroFalhaMoeda]]:
    """Converte indicadores numéricos da Base_de_Municipios para float (R2.3, R2.4).

    **Esta base não está em formato brasileiro.** Diferente do CAGED — onde o
    salário chega como ``"2018,00"``, com vírgula decimal —, o
    `Municipios_SC_limpo.csv` exportado do IBGE usa **ponto decimal**:
    ``0.694`` (IDHM), ``44644.04`` (PIB per capita), ``2628`` (população).
    Aplicar `brl_para_float` aqui destruiria o separador decimal, tratando-o
    como separador de milhar: ``0.694 → 694.0`` e ``44644.04 → 4464404.0``.
    Por isso a conversão usa `pandas.to_numeric`, que lê o ponto decimal
    corretamente (R2.3) e transforma em ``NaN`` tanto o marcador ``"-"`` quanto
    qualquer valor não numérico (R2.4).

    As falhas de conversão são agrupadas por coluna — a Base_de_Municipios não
    possui `competênciamov`, logo não há dimensão de competência.

    Args:
        df: Base_de_Municipios a tratar (não é modificada; uma cópia é
            retornada).
        colunas: indicadores numéricos a converter. Colunas ausentes são
            ignoradas silenciosamente.

    Returns:
        Uma tupla ``(df_convertido, falhas)`` análoga à de `limpar_moeda`.
    """
    resultado = df.copy()
    falhas: list[RegistroFalhaMoeda] = []

    for coluna in colunas:
        if coluna not in resultado.columns:
            continue

        original = resultado[coluna]
        convertido = pd.to_numeric(original, errors="coerce")

        # Falha = origem não era ausente mas o resultado é NaN (valor inválido
        # ou o marcador "-"). Valores já ausentes na origem não contam.
        origem_ausente = original.isna() | (
            original.astype("string").str.strip().isin(["", MARCADOR_AUSENTE])
        )
        falhou = int((convertido.isna() & ~origem_ausente).sum())

        resultado[coluna] = convertido.astype("float64")

        if falhou:
            falhas.append(
                RegistroFalhaMoeda(coluna=coluna, competencia=None, quantidade=falhou)
            )

    return resultado, falhas


@dataclass
class LimpezaResult:
    """Resultado consolidado da orquestração da limpeza (R2.1–R2.9).

    Reúne as bases já tratadas e os logs coletados pelas etapas de limpeza, de
    modo que o notebook orquestrador possa registrá-los e prosseguir para a
    junção relacional.

    Attributes:
        caged: CAGED limpo — moeda convertida, domínios decodificados e filtro
            de competência aplicado.
        municipios: Base_de_Municipios com os indicadores numéricos convertidos
            para ``float`` e o marcador ``"-"`` transformado em ``NaN``.
        falhas_moeda: falhas de conversão monetária do CAGED (R2.2).
        codigos_nao_mapeados: códigos categóricos sem rótulo no dicionário (R2.6).
        falhas_indicadores_municipios: falhas de conversão dos indicadores
            municipais (R2.3/R2.4).
        excluidos_competencia: total de registros do CAGED removidos pelo filtro
            de competência (R2.9).
    """

    caged: pd.DataFrame
    municipios: pd.DataFrame
    falhas_moeda: list[RegistroFalhaMoeda] = field(default_factory=list)
    codigos_nao_mapeados: list[CodigoNaoMapeado] = field(default_factory=list)
    falhas_indicadores_municipios: list[RegistroFalhaMoeda] = field(
        default_factory=list
    )
    excluidos_competencia: int = 0


def limpar(
    df_caged: pd.DataFrame,
    df_municipios: pd.DataFrame,
    mapas: dict[str, dict],
    *,
    inicio: int = COMPETENCIA_INICIO,
    fim: int = COMPETENCIA_FIM,
) -> LimpezaResult:
    """Orquestra a limpeza completa do CAGED e da Base_de_Municipios (R2.1–R2.9).

    Encadeia, sobre o CAGED, a conversão monetária (R2.1/R2.2), a decodificação
    de domínios (R2.5–R2.7) e o filtro de competência (R2.8/R2.9); sobre a
    Base_de_Municipios, converte os indicadores numéricos do formato brasileiro
    para ``float`` e transforma o marcador ``"-"`` em ``NaN`` (R2.3/R2.4). Os
    logs de falha e a contagem de exclusões são reunidos em ``LimpezaResult``.

    A ordem no CAGED — moeda → domínios → competência — garante que as falhas de
    conversão monetária sejam agrupadas pela competência original antes de o
    filtro remover registros, e que o filtro opere sobre a base já tratada.

    Emite uma mensagem única de progresso da etapa de limpeza via
    `logging_pipeline.log_etapa` (base para R8.4).

    Args:
        df_caged: CAGED bruto (não é modificado; cópias intermediárias são
            usadas).
        df_municipios: Base_de_Municipios bruta (não é modificada).
        mapas: dicionários ``{coluna: {codigo: rotulo}}`` de domínio a aplicar.
        inicio: limite inferior inclusivo da competência (AAAAMM).
        fim: limite superior inclusivo da competência (AAAAMM).

    Returns:
        Um ``LimpezaResult`` com as bases limpas e os logs coletados.
    """
    # CAGED: moeda → estoque base → domínios → filtro de competência.
    # O estoque base e o ordinal de escolaridade são derivados **antes** da
    # decodificação porque leem os códigos crus de `tamestabjan` e
    # `graudeinstrução`, que a decodificação substitui pelos rótulos (R4.4, R4.7).
    caged_moeda, falhas_moeda = limpar_moeda(df_caged)
    caged_estoque = derivar_estoque_base(caged_moeda)
    caged_ordinal = derivar_escolaridade_ordinal(caged_estoque)
    caged_dominios, codigos_nao_mapeados = decodificar_dominios(
        caged_ordinal, mapas
    )
    caged_limpo, excluidos_competencia = filtrar_competencia(
        caged_dominios, inicio=inicio, fim=fim
    )

    # Base_de_Municipios: indicadores BR → float; "-" → NaN (R2.3/R2.4).
    municipios_limpo, falhas_indicadores = limpar_indicadores_municipios(
        df_municipios
    )

    resultado = LimpezaResult(
        caged=caged_limpo,
        municipios=municipios_limpo,
        falhas_moeda=falhas_moeda,
        codigos_nao_mapeados=codigos_nao_mapeados,
        falhas_indicadores_municipios=falhas_indicadores,
        excluidos_competencia=excluidos_competencia,
    )

    log_etapa(
        "limpeza",
        (
            f"{len(caged_limpo)} linhas mantidas no CAGED; "
            f"{excluidos_competencia} excluídas por competência; "
            f"{len(falhas_moeda)} grupo(s) de falha monetária; "
            f"{len(codigos_nao_mapeados)} código(s) categórico(s) não mapeado(s)."
        ),
    )

    return resultado


__all__ = [
    "MARCADOR_AUSENTE",
    "COLUNAS_MOEDA_CAGED",
    "COLUNA_TAM_ESTAB_JAN",
    "COLUNA_ESTOQUE_BASE",
    "COLUNA_GRAU_INSTRUCAO",
    "COLUNA_ESCOLARIDADE_ORDINAL",
    "ESCOLARIDADE_ORDINAL",
    "derivar_estoque_base",
    "derivar_escolaridade_ordinal",
    "COLUNA_COMPETENCIA",
    "COMPETENCIA_INICIO",
    "COMPETENCIA_FIM",
    "COLUNAS_INDICADORES_MUNICIPIOS",
    "RegistroFalhaMoeda",
    "CodigoNaoMapeado",
    "LimpezaResult",
    "brl_para_float",
    "limpar_moeda",
    "decodificar_dominios",
    "filtrar_competencia",
    "limpar_indicadores_municipios",
    "limpar",
]
