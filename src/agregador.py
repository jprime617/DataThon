"""Agregador (R6): tabelas agregadas por recorte com indicadores municipais.

Este módulo consolida a base enriquecida (saída da Junta_Relacional +
Classificador_de_CBO, já contendo `saldomovimentação`, `tamestabjan`, `seção`,
`macrofamilia`, `competênciamov` e `chave_municipal`) em uma tabela agregada
pequena, pronta para o dashboard, com **uma linha por combinação distinta de
recorte** (R6.1) e os indicadores socioeconômicos do município anexados (R6.6,
R6.7).

A tarefa 10.1 cobre a **agregação** (R6.1, R6.2, R6.5, R6.6, R6.7):

- `agregar(df_metricas, municipios)`: produz uma linha por
  (região/município × Secao_Industrial × Macrofamilia_CBO × mês), reaproveitando
  as funções puras de ``src/metricas.py`` para calcular Saldo_Liquido,
  Saldo_por_10k, Turnover e Indice_de_Aquecimento no recorte; omite as
  combinações sem registros (R6.2); arredonda as métricas a 2 casas decimais
  (R6.5); e anexa população estimada 2026, IDHM 2010 e PIB per capita 2023 por
  município, com ``NaN`` quando o indicador está ausente (R6.6, R6.7).

Recorte e coluna ``regiao``
---------------------------
O **recorte** da agregação é o município (``chave_municipal`` de 6 dígitos): é a
menor unidade geográfica disponível, o nível em que os indicadores
socioeconômicos existem e a granularidade que o mapa coroplético precisa.

A coluna ``regiao`` é a **mesorregião do IBGE** do município
(`mapeamentos.MESORREGIAO_POR_MUNICIPIO`) — Grande Florianópolis, Norte
Catarinense, Oeste Catarinense, Serrana, Sul Catarinense ou Vale do Itajaí. Ela
é descritiva, não parte da chave: a pergunta de negócio é sobre regiões, e sem
ela o filtro de região do dashboard seria uma lista de 295 códigos municipais.
Nenhuma base de origem traz esse recorte (a coluna ``região`` do CAGED é a
Grande Região do IBGE e vale 4 em todo o estado), daí a tabela de referência.

A chave única de uma linha do agregado é, portanto,
``(municipio, secao_industrial, macrofamilia_cbo, mes)``; ``regiao`` é um
atributo do município, constante dentro dele.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from src import mapeamentos
from src.cbo_ia import COLUNA_MACROFAMILIA, COLUNA_NIVEL
from src.mapeamentos import (
    FAIXA_ESCOLARIDADE_AUSENTE,
    MESORREGIAO_POR_MUNICIPIO,
    MICRORREGIAO_POR_MUNICIPIO,
    REGIAO_DESCONHECIDA,
    SECOES_INDUSTRIAIS,
    SETOR_POR_DIVISAO_TRANSFORMACAO,
    faixa_escolaridade,
)
from src.erros import ErroDeValidacao
from src.logging_pipeline import log_etapa, obter_logger
from src.metricas import (
    COLUNA_CHAVE_MUNICIPAL,
    COLUNA_COMPETENCIA,
    COLUNA_ESCOLARIDADE_MEDIA,
    COLUNA_INDICE_AQUECIMENTO,
    COLUNA_MOVIMENTACAO,
    COLUNA_SALARIO_MEDIO,
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_POR_10K,
    COLUNA_SALDO_MOVIMENTACAO,
    COLUNA_SALARIO,
    COLUNA_ESCOLARIDADE_ORDINAL,
    COLUNA_SECAO,
    COLUNA_TURNOVER,
    MOVIMENTACAO_ADMISSAO,
    MOVIMENTACAO_DESLIGAMENTO,
    escolaridade_media_por_movimentacao,
    indice_aquecimento,
    salario_medio_por_movimentacao,
    saldo_liquido,
    saldo_por_10k,
    turnover,
)

# Nome da etapa usado nas mensagens de log do pipeline (R8.4).
_ETAPA = "agregação"

# Casas decimais das métricas numéricas no agregado (R6.5).
CASAS_DECIMAIS_METRICAS = 2

# --- Colunas do schema de saída da tabela agregada (design, Schema R6) -------
COLUNA_REGIAO = "regiao"
COLUNA_MUNICIPIO = "municipio"
COLUNA_SECAO_INDUSTRIAL = "secao_industrial"
COLUNA_MACROFAMILIA_CBO = "macrofamilia_cbo"
COLUNA_MES = "mes"
COLUNA_SALARIO_MEDIO_ADMISSAO = "salario_medio_admissao"
COLUNA_SALARIO_MEDIO_DESLIGAMENTO = "salario_medio_desligamento"
COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO = "escolaridade_media"
COLUNA_POPULACAO_2026 = "populacao_2026"
COLUNA_IDHM_2010 = "idhm_2010"
COLUNA_PIB_PER_CAPITA_2023 = "pib_per_capita_2023"

# --- Colunas acrescentadas no dashboard v2 (todas aditivas ao schema R6) ----
COLUNA_MICRORREGIAO = "microrregiao"
COLUNA_NOME_MUNICIPIO = "municipio_nome"
COLUNA_SETOR = "setor"
COLUNA_NIVEL_QUALIFICACAO = COLUNA_NIVEL
COLUNA_ESCOPO_INDUSTRIAL = "escopo_industrial"
COLUNA_FAIXA_ESCOLARIDADE = "faixa_escolaridade"

# Contagens e somas por célula: somáveis entre células, de modo que qualquer
# filtro possa ser reagregado e as razões derivadas depois (soma ÷ soma), em
# vez de promediar razões de células de tamanhos muito diferentes.
COLUNA_ADMISSOES = "admissoes"
COLUNA_DESLIGAMENTOS = "desligamentos"
COLUNA_DESLIGAMENTOS_A_PEDIDO = "desligamentos_a_pedido"
COLUNAS_ADITIVAS = [
    COLUNA_ADMISSOES,
    COLUNA_DESLIGAMENTOS,
    COLUNA_DESLIGAMENTOS_A_PEDIDO,
    "soma_salario_admissao",
    "n_salario_admissao",
    "soma_salario_desligamento",
    "n_salario_desligamento",
    "soma_escolaridade_admissao",
    "n_escolaridade_admissao",
    "soma_escolaridade_desligamento",
    "n_escolaridade_desligamento",
]

# Coluna de tipo de movimentação do CAGED e o código do desligamento a pedido
# (40), aceito cru ou já decodificado pelo Limpador.
COLUNA_TIPO_MOVIMENTACAO = "tipomovimentação"
CODIGO_DESLIGAMENTO_A_PEDIDO = 40
COLUNA_SUBCLASSE = "subclasse"

# Rótulo de nível quando a base não traz o nível de qualificação da CBO.
NIVEL_NAO_INFORMADO = "Não informado"

# Medianas salariais do perfil (não aditivas: calculadas no pipeline).
COLUNA_MEDIANA_SALARIO_ADMISSAO = "mediana_salario_admissao"
COLUNA_MEDIANA_SALARIO_DESLIGAMENTO = "mediana_salario_desligamento"

# --- Colunas de origem dos indicadores municipais (cabeçalho da base) --------
# Os nomes seguem exatamente `limpeza.COLUNAS_INDICADORES_MUNICIPIOS`, que por
# sua vez reproduzem o cabeçalho de `Municipios_SC_limpo.csv` (R6.6).
ORIGEM_POPULACAO_2026 = "População estimada - pessoas [2026]"
ORIGEM_IDHM_2010 = (
    "IDHM <span>Índice de desenvolvimento humano municipal</span> [2010]"
)
ORIGEM_PIB_PER_CAPITA_2023 = "PIB per capita - R$ [2023]"

# Mapa coluna de saída do indicador → coluna de origem na Base_de_Municipios.
_INDICADORES = {
    COLUNA_POPULACAO_2026: ORIGEM_POPULACAO_2026,
    COLUNA_IDHM_2010: ORIGEM_IDHM_2010,
    COLUNA_PIB_PER_CAPITA_2023: ORIGEM_PIB_PER_CAPITA_2023,
}

# Colunas de recorte da agregação na base enriquecida de entrada (R6.1).
# O recorte geográfico é o município (Chave_Municipal); ver docstring do módulo.
_COLUNAS_RECORTE = [
    COLUNA_CHAVE_MUNICIPAL,
    COLUNA_SECAO,
    COLUNA_SETOR,
    COLUNA_MACROFAMILIA,
    COLUNA_NIVEL,
    COLUNA_COMPETENCIA,
]

# Ordem final das colunas do agregado, conforme o schema do design (R6).
_COLUNAS_SAIDA = [
    COLUNA_REGIAO,
    COLUNA_MUNICIPIO,
    COLUNA_SECAO_INDUSTRIAL,
    COLUNA_MACROFAMILIA_CBO,
    COLUNA_MES,
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_POR_10K,
    COLUNA_TURNOVER,
    COLUNA_INDICE_AQUECIMENTO,
    COLUNA_SALARIO_MEDIO_ADMISSAO,
    COLUNA_SALARIO_MEDIO_DESLIGAMENTO,
    COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO,
    COLUNA_POPULACAO_2026,
    COLUNA_IDHM_2010,
    COLUNA_PIB_PER_CAPITA_2023,
    # v2: dimensões e contagens aditivas, sempre DEPOIS das colunas R6 para que
    # o app antigo continue lendo o mesmo schema.
    COLUNA_NOME_MUNICIPIO,
    COLUNA_MICRORREGIAO,
    COLUNA_SETOR,
    COLUNA_NIVEL_QUALIFICACAO,
    COLUNA_ESCOPO_INDUSTRIAL,
    *COLUNAS_ADITIVAS,
]

# Métricas numéricas arredondadas a 2 casas na saída (R6.5).
_COLUNAS_METRICAS = [
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_POR_10K,
    COLUNA_TURNOVER,
    COLUNA_INDICE_AQUECIMENTO,
    COLUNA_SALARIO_MEDIO_ADMISSAO,
    COLUNA_SALARIO_MEDIO_DESLIGAMENTO,
    COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO,
]


def _rotulos_secoes_industriais() -> set[str]:
    """Letras B–F e os rótulos decodificados correspondentes do dicionário."""
    rotulos = set(SECOES_INDUSTRIAIS)
    try:
        rotulos |= {mapeamentos.SECAO_CNAE[letra] for letra in SECOES_INDUSTRIAIS}
    except Exception:  # noqa: BLE001 — sem dicionário, valem só as letras
        pass
    return rotulos


def _eh_transformacao(secao: pd.Series) -> pd.Series:
    """Linhas da seção C, pela letra ou pelo rótulo decodificado."""
    try:
        rotulo_c = mapeamentos.SECAO_CNAE["C"]
    except Exception:  # noqa: BLE001
        rotulo_c = "C"
    return secao.isin({"C", rotulo_c})


# Salário válido para as somas e medianas v2: > 0 e até este múltiplo da mediana
# estadual dos salários positivos. A base traz desligamentos com "salário" de
# R$ 1,1 milhão (rescisão ou digitação) e ~34 mil zeros, que distorcem médias.
MULTIPLO_TETO_SALARIO = 20


def teto_salario(df: pd.DataFrame) -> float:
    """Teto de salário válido: `MULTIPLO_TETO_SALARIO` × mediana dos positivos."""
    if COLUNA_SALARIO not in df.columns:
        return float("inf")
    salario = pd.to_numeric(df[COLUNA_SALARIO], errors="coerce")
    positivos = salario[salario > 0]
    return float(positivos.median() * MULTIPLO_TETO_SALARIO) if len(positivos) else float("inf")


def preparar_base(df: pd.DataFrame, teto: float | None = None) -> pd.DataFrame:
    """Acrescenta à base as dimensões v2 e os indicadores somáveis por linha.

    - ``setor``: a divisão CNAE agrupada (PLANEJAMENTO §4.2) dentro da seção C;
      nas demais seções, o próprio rótulo da seção.
    - ``nivel_qualificacao``: o nível da CBO (já mesclado pela etapa de IA);
      ausente → `NIVEL_NAO_INFORMADO`.
    - indicadores 0/1 de admissão, desligamento e desligamento a pedido (40) e
      os salários válidos (> 0 e ≤ `teto_salario`) e as escolaridades não
      nulas, com os seus contadores.
    """
    teto = teto_salario(df) if teto is None else teto
    # Só as colunas usadas: copiar a base inteira (3,4 mi linhas de texto)
    # dobrava o pico de memória do pipeline.
    usadas = [
        COLUNA_CHAVE_MUNICIPAL, COLUNA_SECAO, COLUNA_SUBCLASSE, COLUNA_MACROFAMILIA,
        COLUNA_NIVEL, COLUNA_COMPETENCIA, COLUNA_SALDO_MOVIMENTACAO,
        COLUNA_TIPO_MOVIMENTACAO, COLUNA_SALARIO, COLUNA_ESCOLARIDADE_ORDINAL,
    ]
    base = df[[c for c in usadas if c in df.columns]].copy()
    secao = base[COLUNA_SECAO]
    if COLUNA_SUBCLASSE in base.columns:
        divisao = pd.to_numeric(base[COLUNA_SUBCLASSE], errors="coerce") // 100_000
        setor_c = divisao.map(SETOR_POR_DIVISAO_TRANSFORMACAO)
        base[COLUNA_SETOR] = secao.where(
            ~_eh_transformacao(secao) | setor_c.isna(), setor_c
        )
    else:
        base[COLUNA_SETOR] = secao
    if COLUNA_NIVEL not in base.columns:
        base[COLUNA_NIVEL] = NIVEL_NAO_INFORMADO
    base[COLUNA_NIVEL] = base[COLUNA_NIVEL].fillna(NIVEL_NAO_INFORMADO)

    mov = pd.to_numeric(base[COLUNA_SALDO_MOVIMENTACAO], errors="coerce")
    adm, desl = mov == 1, mov == -1
    if COLUNA_TIPO_MOVIMENTACAO in base.columns:
        tipo = base[COLUNA_TIPO_MOVIMENTACAO]
        rotulo = "Desligamento a pedido"
        try:
            rotulo = mapeamentos.TIPO_MOVIMENTACAO[CODIGO_DESLIGAMENTO_A_PEDIDO]
        except Exception:  # noqa: BLE001
            pass
        a_pedido = tipo.isin({CODIGO_DESLIGAMENTO_A_PEDIDO, "40", rotulo})
    else:
        a_pedido = pd.Series(False, index=base.index)
    base[COLUNA_ADMISSOES] = adm.astype("int64")
    base[COLUNA_DESLIGAMENTOS] = desl.astype("int64")
    base[COLUNA_DESLIGAMENTOS_A_PEDIDO] = (desl & a_pedido).astype("int64")

    for origem, nome in ((COLUNA_SALARIO, "salario"), (COLUNA_ESCOLARIDADE_ORDINAL, "escolaridade")):
        valor = (
            pd.to_numeric(base[origem], errors="coerce")
            if origem in base.columns
            else pd.Series(float("nan"), index=base.index)
        )
        if nome == "salario":
            valor = valor.where((valor > 0) & (valor <= teto))
        for mascara, sufixo in ((adm, "admissao"), (desl, "desligamento")):
            valido = mascara & valor.notna()
            base[f"soma_{nome}_{sufixo}"] = valor.where(valido, 0.0)
            base[f"n_{nome}_{sufixo}"] = valido.astype("int64")
    return base


def agregar(df_metricas: pd.DataFrame, municipios: pd.DataFrame) -> pd.DataFrame:
    """Agrega a base enriquecida por recorte e anexa indicadores municipais (R6).

    Produz uma tabela com **uma linha por combinação distinta** de município
    (``chave_municipal``), Secao_Industrial (``seção``), Macrofamilia_CBO
    (``macrofamilia``) e mês (``competênciamov``) (R6.1), acrescida da
    mesorregião do município na coluna ``regiao``.
    Apenas as combinações presentes em ``df_metricas`` geram linha — recortes
    sem registros são naturalmente omitidos pela agregação (R6.2).

    Para cada recorte, reaproveita as funções puras de ``src/metricas.py``:

    - `saldo_liquido` — Saldo_Liquido por (município × seção × macrofamília × mês);
    - `saldo_por_10k` — normaliza o saldo pela população estimada 2026 (``NaN``
      quando a população é ausente ou não positiva);
    - `turnover` — rotatividade por (município × seção × macrofamília) replicada
      a cada mês do recorte (o estoque base é característica do recorte, não do
      mês);
    - `indice_aquecimento` — Saldo_por_10k somado à variação mensal do
      Saldo_Liquido dentro de cada (município × seção × macrofamília).

    As quatro métricas são arredondadas a 2 casas decimais (R6.5). Por fim,
    anexa os indicadores de população estimada 2026, IDHM 2010 e PIB per capita
    2023 do município (R6.6); municípios sem o indicador na base — ou sem linha
    na Base_de_Municipios — recebem ``NaN`` sem interromper a agregação (R6.7).

    Quando ``df_metricas`` é vazio, o retorno é um DataFrame vazio com o schema
    de saída (nenhum recorte a reportar — R6.2).

    Args:
        df_metricas: base enriquecida (cruzada + macrofamília), com as colunas de
            recorte ``chave_municipal``, ``seção``, ``macrofamilia`` e
            ``competênciamov``, além de ``saldomovimentação`` e ``tamestabjan``
            para o cálculo das métricas. Não é modificada.
        municipios: Base_de_Municipios tratada, com ``chave_municipal`` e os
            indicadores socioeconômicos (população 2026, IDHM 2010, PIB per
            capita 2023). Não é modificada.

    Returns:
        Um DataFrame com as colunas do schema agregado (R6): ``regiao``,
        ``municipio``, ``secao_industrial``, ``macrofamilia_cbo``, ``mes``,
        ``saldo_liquido``, ``saldo_por_10k``, ``turnover``,
        ``indice_aquecimento``, ``populacao_2026``, ``idhm_2010`` e
        ``pib_per_capita_2023``.

    Raises:
        KeyError: se alguma coluna de recorte ou coluna necessária às métricas
            estiver ausente em ``df_metricas``, ou se ``chave_municipal`` faltar
            em ``municipios``.
    """
    # `setor` e `nivel_qualificacao` são derivados por `preparar_base`.
    obrigatorias = [c for c in _COLUNAS_RECORTE if c not in (COLUNA_SETOR, COLUNA_NIVEL)]
    faltando = [c for c in obrigatorias if c not in df_metricas.columns]
    if faltando:
        raise KeyError(
            "Colunas de recorte ausentes em 'df_metricas' para a agregação: "
            f"{faltando}."
        )
    if COLUNA_CHAVE_MUNICIPAL not in municipios.columns:
        raise KeyError(
            "Coluna 'chave_municipal' ausente em 'municipios' para anexar os "
            "indicadores socioeconômicos."
        )

    if df_metricas.empty:
        # Sem registros, não há recorte a agregar (R6.2).
        vazio = pd.DataFrame(columns=_COLUNAS_SAIDA)
        log_etapa(_ETAPA, "0 recortes agregados (base de métricas vazia).")
        return vazio

    df_metricas = preparar_base(df_metricas)

    # --- Métricas por recorte, reaproveitando metricas.py (R6.5) -------------
    # Saldo_Liquido no recorte completo (município × seção × macrofamília × mês).
    saldo = saldo_liquido(df_metricas, _COLUNAS_RECORTE)

    # Saldo_por_10k: normaliza pela população 2026 do município (R4.2/4.3).
    saldo = saldo_por_10k(saldo, municipios)

    # Indice_de_Aquecimento: soma nível + variação mensal dentro de cada
    # (município × seção × macrofamília); `indice_aquecimento` usa como recorte
    # todas as colunas que não são competência nem métricas de saldo, o que
    # corresponde exatamente ao recorte sem o mês (R4.8/4.9).
    saldo = indice_aquecimento(saldo)

    # Turnover por (município × seção × macrofamília); replicado a cada mês do
    # recorte via merge, pois o estoque base não varia por mês (R4.4/4.5).
    por_turnover = [c for c in _COLUNAS_RECORTE if c != COLUNA_COMPETENCIA]
    turn = turnover(df_metricas, por_turnover)

    agregado = saldo.merge(turn, how="left", on=por_turnover)

    # Salário médio e escolaridade média no mesmo recorte, para que a dispersão
    # renda × escolaridade do dashboard (R7.4) tenha fonte e responda aos mesmos
    # filtros das demais visualizações (R4.6, R4.7).
    agregado = _anexar_renda_escolaridade(agregado, df_metricas)

    # Contagens e somas aditivas por célula (dashboard v2).
    aditivas = (
        df_metricas.groupby(_COLUNAS_RECORTE, dropna=False)[COLUNAS_ADITIVAS]
        .sum()
        .reset_index()
    )
    agregado = agregado.merge(aditivas, how="left", on=_COLUNAS_RECORTE)

    # --- Mapeia para o schema de saída (design, Schema R6) -------------------
    resultado = pd.DataFrame(
        {
            # Mesorregião do IBGE do município (ver docstring do módulo); o
            # município permanece como a unidade geográfica fina do mapa.
            COLUNA_REGIAO: agregado[COLUNA_CHAVE_MUNICIPAL].map(
                lambda chave: MESORREGIAO_POR_MUNICIPIO.get(
                    str(chave), REGIAO_DESCONHECIDA
                )
            ),
            COLUNA_MUNICIPIO: agregado[COLUNA_CHAVE_MUNICIPAL],
            COLUNA_SECAO_INDUSTRIAL: agregado[COLUNA_SECAO],
            COLUNA_MACROFAMILIA_CBO: agregado[COLUNA_MACROFAMILIA],
            COLUNA_MES: agregado[COLUNA_COMPETENCIA],
            COLUNA_SALDO_LIQUIDO: agregado[COLUNA_SALDO_LIQUIDO],
            COLUNA_SALDO_POR_10K: agregado[COLUNA_SALDO_POR_10K],
            COLUNA_TURNOVER: agregado[COLUNA_TURNOVER],
            COLUNA_INDICE_AQUECIMENTO: agregado[COLUNA_INDICE_AQUECIMENTO],
            COLUNA_SALARIO_MEDIO_ADMISSAO: agregado[COLUNA_SALARIO_MEDIO_ADMISSAO],
            COLUNA_SALARIO_MEDIO_DESLIGAMENTO: agregado[
                COLUNA_SALARIO_MEDIO_DESLIGAMENTO
            ],
            COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO: agregado[
                COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO
            ],
            COLUNA_MICRORREGIAO: agregado[COLUNA_CHAVE_MUNICIPAL].map(
                lambda chave: MICRORREGIAO_POR_MUNICIPIO.get(
                    str(chave), REGIAO_DESCONHECIDA
                )
            ),
            COLUNA_SETOR: agregado[COLUNA_SETOR],
            COLUNA_NIVEL_QUALIFICACAO: agregado[COLUNA_NIVEL],
            COLUNA_ESCOPO_INDUSTRIAL: agregado[COLUNA_SECAO].isin(
                _rotulos_secoes_industriais()
            ),
            **{coluna: agregado[coluna] for coluna in COLUNAS_ADITIVAS},
        }
    )
    for coluna in COLUNAS_ADITIVAS:
        if coluna.startswith("soma_"):
            resultado[coluna] = resultado[coluna].astype("float64").round(
                CASAS_DECIMAIS_METRICAS
            )
        else:
            resultado[coluna] = resultado[coluna].astype("int64")

    # Arredonda as métricas a 2 casas decimais, preservando NaN (R6.5).
    for coluna in _COLUNAS_METRICAS:
        resultado[coluna] = resultado[coluna].astype("float64").round(
            CASAS_DECIMAIS_METRICAS
        )

    # --- Anexa os indicadores municipais por chave_municipal (R6.6, R6.7) ----
    resultado = _anexar_indicadores(resultado, agregado, municipios)

    resultado = resultado[_COLUNAS_SAIDA].reset_index(drop=True)

    log_etapa(
        _ETAPA,
        (
            f"{len(resultado)} recortes agregados "
            f"(município × seção × macrofamília × mês) em "
            f"{resultado[COLUNA_REGIAO].nunique()} mesorregião(ões)."
        ),
    )
    return resultado


def _anexar_renda_escolaridade(
    agregado: pd.DataFrame, df_metricas: pd.DataFrame
) -> pd.DataFrame:
    """Anexa salário médio (admissão/desligamento) e escolaridade média (R4.6, R4.7).

    Calcula as médias no **mesmo recorte** do agregado, reaproveitando as funções
    puras de ``src/metricas.py``, e pivota a dimensão ``movimentação`` em colunas:
    ``salario_medio_admissao``, ``salario_medio_desligamento`` e
    ``escolaridade_media`` (da admissão — é a entrada do mercado, que é o que a
    leitura de qualificação quer medir).

    Degrada preservando o schema: se a base não trouxer `salário` ou
    `escolaridade_ordinal` — caso de bases sintéticas e de testes de recorte —, as
    colunas correspondentes saem inteiramente ``NaN`` em vez de quebrar a
    agregação, do mesmo modo que `_anexar_indicadores` faz com um indicador
    municipal ausente (R6.7).

    Args:
        agregado: DataFrame de recortes já com as métricas de saldo/turnover.
        df_metricas: base enriquecida de origem.

    Returns:
        O ``agregado`` acrescido das três colunas.
    """
    resultado = agregado.copy()
    ausente = pd.Series([float("nan")] * len(resultado), index=resultado.index)

    # --- Salário médio por movimentação (R4.6) ---
    if COLUNA_SALARIO in df_metricas.columns:
        salarios = salario_medio_por_movimentacao(df_metricas, por=_COLUNAS_RECORTE)
        for coluna_saida, rotulo in (
            (COLUNA_SALARIO_MEDIO_ADMISSAO, MOVIMENTACAO_ADMISSAO),
            (COLUNA_SALARIO_MEDIO_DESLIGAMENTO, MOVIMENTACAO_DESLIGAMENTO),
        ):
            fatia = salarios.loc[
                salarios[COLUNA_MOVIMENTACAO] == rotulo,
                [*_COLUNAS_RECORTE, COLUNA_SALARIO_MEDIO],
            ].rename(columns={COLUNA_SALARIO_MEDIO: coluna_saida})
            resultado = resultado.merge(fatia, how="left", on=_COLUNAS_RECORTE)
    else:
        resultado[COLUNA_SALARIO_MEDIO_ADMISSAO] = ausente
        resultado[COLUNA_SALARIO_MEDIO_DESLIGAMENTO] = ausente

    # --- Escolaridade média dos admitidos (R4.7) ---
    if COLUNA_ESCOLARIDADE_ORDINAL in df_metricas.columns:
        escolaridade = escolaridade_media_por_movimentacao(
            df_metricas, por=_COLUNAS_RECORTE
        )
        fatia = escolaridade.loc[
            escolaridade[COLUNA_MOVIMENTACAO] == MOVIMENTACAO_ADMISSAO,
            [*_COLUNAS_RECORTE, COLUNA_ESCOLARIDADE_MEDIA],
        ].rename(
            columns={COLUNA_ESCOLARIDADE_MEDIA: COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO}
        )
        resultado = resultado.merge(fatia, how="left", on=_COLUNAS_RECORTE)
    else:
        resultado[COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO] = ausente

    return resultado


def _anexar_indicadores(
    resultado: pd.DataFrame,
    agregado: pd.DataFrame,
    municipios: pd.DataFrame,
) -> pd.DataFrame:
    """Anexa população 2026, IDHM 2010 e PIB per capita 2023 por município (R6.6).

    Monta, para cada indicador, um mapa ``chave_municipal → valor`` (uma entrada
    por município) a partir da Base_de_Municipios e o aplica à chave de cada
    recorte. Municípios ausentes na base — ou cujo indicador não existe na base —
    recebem ``NaN`` (R6.7). Indicadores que não constam do cabeçalho da base
    resultam numa coluna inteiramente ``NaN``, preservando o schema de saída.

    Args:
        resultado: DataFrame de saída já com as métricas mapeadas.
        agregado: DataFrame intermediário que ainda carrega ``chave_municipal``
            alinhada linha a linha com ``resultado``.
        municipios: Base_de_Municipios tratada.

    Returns:
        O ``resultado`` acrescido das três colunas de indicadores.
    """
    chaves = agregado[COLUNA_CHAVE_MUNICIPAL]
    # Nome do município (cabeçalho "Município" ou "Município [-]"); o painel
    # não pode depender de `Dados/`, que não vai no pacote de deploy.
    from src.enriquecimento import _nome_base

    coluna_nome = next(
        (c for c in municipios.columns if _nome_base(c) == "Município"), None
    )
    if coluna_nome is not None:
        nomes = (
            municipios[[COLUNA_CHAVE_MUNICIPAL, coluna_nome]]
            .drop_duplicates(subset=COLUNA_CHAVE_MUNICIPAL)
            .set_index(COLUNA_CHAVE_MUNICIPAL)[coluna_nome]
        )
        resultado[COLUNA_NOME_MUNICIPIO] = chaves.map(nomes).fillna(chaves).astype(str).values
    else:
        resultado[COLUNA_NOME_MUNICIPIO] = chaves.astype(str).values
    for coluna_saida, coluna_origem in _INDICADORES.items():
        if coluna_origem in municipios.columns:
            mapa = (
                municipios[[COLUNA_CHAVE_MUNICIPAL, coluna_origem]]
                .drop_duplicates(subset=COLUNA_CHAVE_MUNICIPAL)
                .set_index(COLUNA_CHAVE_MUNICIPAL)[coluna_origem]
            )
            valores = chaves.map(mapa)
        else:
            # Indicador ausente da base → coluna inteiramente ausente (R6.7).
            valores = pd.Series([pd.NA] * len(chaves), index=chaves.index)
        resultado[coluna_saida] = pd.to_numeric(
            valores, errors="coerce"
        ).astype("float64").values
    return resultado


# Dimensões do perfil (causa raiz): período inteiro, sem município nem mês.
COLUNAS_PERFIL = [
    COLUNA_REGIAO,
    COLUNA_SECAO_INDUSTRIAL,
    COLUNA_SETOR,
    COLUNA_ESCOPO_INDUSTRIAL,
    COLUNA_MACROFAMILIA_CBO,
    COLUNA_NIVEL_QUALIFICACAO,
    COLUNA_FAIXA_ESCOLARIDADE,
]


def agregar_perfil(df_metricas: pd.DataFrame) -> pd.DataFrame:
    """Tabela de perfil para a causa raiz (PLANEJAMENTO §4.4, §6).

    Uma linha por mesorregião × seção × setor × macrofamília × nível ×
    faixa de escolaridade (do próprio trabalhador movimentado), no período
    inteiro, com as mesmas colunas aditivas do agregado e as **medianas**
    salariais de admissão e desligamento — que não são somáveis e por isso só
    podem ser calculadas aqui, sobre os microdados.
    """
    base = preparar_base(df_metricas)
    base[COLUNA_REGIAO] = base[COLUNA_CHAVE_MUNICIPAL].map(
        lambda chave: MESORREGIAO_POR_MUNICIPIO.get(str(chave), REGIAO_DESCONHECIDA)
    )
    base[COLUNA_ESCOPO_INDUSTRIAL] = base[COLUNA_SECAO].isin(
        _rotulos_secoes_industriais()
    )
    ordinal = (
        pd.to_numeric(base[COLUNA_ESCOLARIDADE_ORDINAL], errors="coerce")
        if COLUNA_ESCOLARIDADE_ORDINAL in base.columns
        else pd.Series(float("nan"), index=base.index)
    )
    base[COLUNA_FAIXA_ESCOLARIDADE] = ordinal.map(faixa_escolaridade)
    base = base.rename(
        columns={
            COLUNA_SECAO: COLUNA_SECAO_INDUSTRIAL,
            COLUNA_MACROFAMILIA: COLUNA_MACROFAMILIA_CBO,
        }
    )
    grupos = base.groupby(COLUNAS_PERFIL, dropna=False)
    perfil = grupos[COLUNAS_ADITIVAS].sum()

    teto = teto_salario(df_metricas)
    salario = (
        pd.to_numeric(base[COLUNA_SALARIO], errors="coerce")
        if COLUNA_SALARIO in base.columns
        else pd.Series(float("nan"), index=base.index)
    )
    salario = salario.where((salario > 0) & (salario <= teto))
    for indicador, coluna in (
        (COLUNA_ADMISSOES, COLUNA_MEDIANA_SALARIO_ADMISSAO),
        (COLUNA_DESLIGAMENTOS, COLUNA_MEDIANA_SALARIO_DESLIGAMENTO),
    ):
        perfil[coluna] = (
            salario.where(base[indicador] == 1)
            .groupby([base[c] for c in COLUNAS_PERFIL], dropna=False)
            .median()
        )
    perfil = perfil.reset_index()
    for coluna in perfil.columns:
        if coluna.startswith(("soma_", "mediana_")):
            perfil[coluna] = perfil[coluna].astype("float64").round(CASAS_DECIMAIS_METRICAS)
    log_etapa(_ETAPA, f"perfil de causa raiz com {len(perfil)} linhas.")
    return perfil


def montar_metadados(
    *,
    linhas_brutas: int,
    linhas_limpas: int,
    excluidas_competencia: int,
    df_agregado: pd.DataFrame,
    df_perfil: pd.DataFrame,
    meta_ia: dict | None = None,
    raiz: str | os.PathLike[str] = ".",
    teto_salario_valido: float | None = None,
) -> dict:
    """Reúne a procedência dos artefatos para o `metadados.json`.

    Os volumes de movimentação saem do próprio agregado (soma das contagens),
    de modo que o funil exibido no painel seja coerente com o que ele agrega.
    """
    import subprocess

    def _comando(*args: str) -> str | None:
        try:
            saida = subprocess.run(
                args, cwd=raiz, capture_output=True, text=True, timeout=120, check=True
            )
            return saida.stdout.strip()
        except Exception:  # noqa: BLE001 — procedência é melhor-esforço
            return None

    movimentos = df_agregado[COLUNA_ADMISSOES] + df_agregado[COLUNA_DESLIGAMENTOS]
    industria = df_agregado[COLUNA_ESCOPO_INDUSTRIAL].astype(bool)
    nao_classificado = df_agregado[COLUNA_MACROFAMILIA_CBO] == mapeamentos.NAO_CLASSIFICADO
    meses = sorted(df_agregado[COLUNA_MES].astype(str).unique())
    coleta = _comando("python", "-m", "pytest", "--collect-only", "-q")
    n_testes = None
    if coleta:
        for linha in reversed(coleta.splitlines()):
            if "collected" in linha or "test" in linha:
                numeros = [int(t) for t in linha.split() if t.isdigit()]
                if numeros:
                    n_testes = numeros[0]
                    break
    return {
        "gerado_em": pd.Timestamp.now(tz="America/Sao_Paulo").isoformat(timespec="seconds"),
        "periodo": {"inicio": meses[0] if meses else None, "fim": meses[-1] if meses else None, "meses": len(meses)},
        "commit": _comando("git", "rev-parse", "--short", "HEAD"),
        "linhas": {
            "brutas": int(linhas_brutas),
            "excluidas_competencia": int(excluidas_competencia),
            "apos_limpeza": int(linhas_limpas),
            "movimentacoes_agregadas": int(movimentos.sum()),
            "movimentacoes_industria": int(movimentos[industria].sum()),
            "agregado": int(len(df_agregado)),
            "perfil": int(len(df_perfil)),
        },
        "ia": {
            **(meta_ia or {}),
            "nao_classificado_ponderado": float(movimentos[nao_classificado].sum() / movimentos.sum())
            if movimentos.sum()
            else None,
        },
        "salario_valido": {
            "regra": f"> 0 e ≤ {MULTIPLO_TETO_SALARIO} × mediana estadual dos salários positivos",
            "teto": teto_salario_valido,
        },
        "testes": n_testes,
    }


def escrever_metadados(destino: str | os.PathLike[str], metadados: dict) -> None:
    """Grava o `metadados.json` (procedência dos artefatos) de forma atômica."""
    import json

    caminho = Path(destino)
    temporario = caminho.with_name(f"{caminho.name}.tmp")
    temporario.write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporario, caminho)
    log_etapa(_ETAPA, f"metadados gravados em '{caminho}'.")


# Extensões de arquivo suportadas na exportação do agregado (R6.3).
EXTENSAO_PARQUET = ".parquet"
EXTENSAO_CSV = ".csv"
_EXTENSOES_SUPORTADAS = (EXTENSAO_PARQUET, EXTENSAO_CSV)


def exportar(df_agregado: pd.DataFrame, destino: str | os.PathLike[str]) -> None:
    """Exporta a tabela agregada para Parquet ou CSV, sem deixar arquivo parcial.

    O formato de saída é escolhido pela **extensão** de ``destino`` (R6.3):

    - ``.parquet`` → grava via ``DataFrame.to_parquet`` (colunar, pyarrow);
    - ``.csv`` → grava via ``DataFrame.to_csv`` (``utf-8``, sem índice).

    Para honrar a "falha explícita e cedo" do design (R6.4), a gravação é feita
    primeiro em um arquivo temporário no mesmo diretório do ``destino`` e só é
    promovida para o caminho final com um ``os.replace`` atômico após terminar
    com sucesso. Se qualquer etapa falhar — extensão não suportada, erro de
    serialização, diretório inexistente, permissão negada —, o temporário é
    removido, um erro identificando o ``destino`` é registrado no log e um
    `ErroDeValidacao` é levantado. Assim, nenhum arquivo parcial permanece: ou o
    ``destino`` existe íntegro, ou não existe nova gravação.

    Args:
        df_agregado: tabela agregada (saída de :func:`agregar`) a exportar. Não
            é modificada.
        destino: caminho do arquivo de saída; a extensão (``.parquet`` ou
            ``.csv``) determina o formato.

    Raises:
        ErroDeValidacao: se a extensão de ``destino`` não for suportada ou se a
            gravação falhar por qualquer motivo. A mensagem identifica o
            ``destino`` e nenhum arquivo parcial é deixado para trás.
    """
    caminho = Path(destino)
    extensao = caminho.suffix.lower()
    logger = obter_logger()

    if extensao not in _EXTENSOES_SUPORTADAS:
        mensagem = (
            f"Falha ao exportar a agregação para '{caminho}': extensão "
            f"'{extensao or '(sem extensão)'}' não suportada; use "
            f"{EXTENSAO_PARQUET} ou {EXTENSAO_CSV} (R6.3)."
        )
        logger.error(mensagem)
        raise ErroDeValidacao(mensagem)

    # Grava num temporário no mesmo diretório para que o `os.replace` final seja
    # atômico (mesmo sistema de arquivos) e nunca exponha conteúdo parcial.
    temporario = caminho.with_name(f"{caminho.name}.tmp")
    try:
        if extensao == EXTENSAO_PARQUET:
            df_agregado.to_parquet(temporario, index=False)
        else:  # EXTENSAO_CSV
            df_agregado.to_csv(temporario, index=False, encoding="utf-8")
        os.replace(temporario, caminho)
    except Exception as erro:
        # Remove o temporário para não deixar arquivo parcial (R6.4); o destino
        # final permanece intocado caso já existisse de uma exportação anterior.
        try:
            if temporario.exists():
                temporario.unlink()
        except OSError:
            # Falha na limpeza não deve mascarar o erro original de exportação.
            pass
        mensagem = (
            f"Falha ao exportar a agregação para '{caminho}': {erro} "
            f"(nenhum arquivo parcial foi gravado — R6.4)."
        )
        logger.error(mensagem)
        raise ErroDeValidacao(mensagem) from erro

    log_etapa(
        _ETAPA,
        f"agregado exportado para '{caminho}' ({len(df_agregado)} linhas).",
    )


__all__ = [
    "CASAS_DECIMAIS_METRICAS",
    "COLUNA_REGIAO",
    "COLUNA_MUNICIPIO",
    "COLUNA_SECAO_INDUSTRIAL",
    "COLUNA_MACROFAMILIA_CBO",
    "COLUNA_MES",
    "COLUNA_SALARIO_MEDIO_ADMISSAO",
    "COLUNA_SALARIO_MEDIO_DESLIGAMENTO",
    "COLUNA_ESCOLARIDADE_MEDIA_ADMISSAO",
    "COLUNA_POPULACAO_2026",
    "COLUNA_IDHM_2010",
    "COLUNA_PIB_PER_CAPITA_2023",
    "ORIGEM_POPULACAO_2026",
    "ORIGEM_IDHM_2010",
    "ORIGEM_PIB_PER_CAPITA_2023",
    "EXTENSAO_PARQUET",
    "EXTENSAO_CSV",
    "COLUNA_MICRORREGIAO",
    "COLUNA_NOME_MUNICIPIO",
    "COLUNA_SETOR",
    "COLUNA_NIVEL_QUALIFICACAO",
    "COLUNA_ESCOPO_INDUSTRIAL",
    "COLUNA_FAIXA_ESCOLARIDADE",
    "COLUNA_ADMISSOES",
    "COLUNA_DESLIGAMENTOS",
    "COLUNA_DESLIGAMENTOS_A_PEDIDO",
    "COLUNA_MEDIANA_SALARIO_ADMISSAO",
    "COLUNA_MEDIANA_SALARIO_DESLIGAMENTO",
    "COLUNAS_ADITIVAS",
    "COLUNAS_PERFIL",
    "preparar_base",
    "teto_salario",
    "MULTIPLO_TETO_SALARIO",
    "agregar",
    "agregar_perfil",
    "escrever_metadados",
    "montar_metadados",
    "exportar",
]
