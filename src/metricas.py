"""Calculador_de_Metricas (R4): métricas de negócio do mercado de trabalho.

Este módulo expõe **funções puras** sobre DataFrames já cruzados e enriquecidos
(saída da Junta_Relacional e do Classificador_de_CBO). Nenhuma função realiza
I/O: todas recebem e devolvem DataFrames, o que viabiliza o property-based
testing das métricas.

Admissão corresponde a ``saldomovimentação == +1`` e desligamento a
``saldomovimentação == -1`` (R4.1).

Métricas cobertas até aqui:

- `saldo_liquido`: soma algébrica de `saldomovimentação` por recorte declarado
  (ex.: município × Secao_Industrial × mês); um recorte sem admissões nem
  desligamentos tem saldo ``0`` (R4.1, R4.10).
- `saldo_por_10k`: normaliza o Saldo_Liquido pela população estimada 2026 do
  município — ``(saldo / populacao) * 10_000`` quando a população é maior que
  zero, ou ``NaN`` quando a população está ausente ou é zero (R4.2, R4.3).
- `turnover`: rotatividade por recorte (município × Secao_Industrial) como
  ``min(admissões, desligamentos) / estoque_base`` limitada ao intervalo
  ``[0, 1]``; ``NaN`` quando o estoque base é zero ou ausente (R4.4, R4.5).
"""

from __future__ import annotations

import math

import pandas as pd

# Coluna de movimentação do CAGED: +1 admissão, -1 desligamento (R4.1).
COLUNA_SALDO_MOVIMENTACAO = "saldomovimentação"

# Coluna do estoque base de vínculos ativos no início do período — denominador
# do Turnover (R4.4). É a coluna **derivada** por `limpeza.derivar_estoque_base`
# a partir do código de faixa de `tamestabjan`, já em número de vínculos. A
# coluna `tamestabjan` original fica com o rótulo legível da faixa (R2.5) e não
# serve como denominador: é um código de 1 a 10, não uma contagem.
COLUNA_ESTOQUE_BASE = "estoque_base"

# Nome da coluna de turnover produzida por `turnover` (R4.4).
COLUNA_TURNOVER = "turnover"

# Nome da coluna de saldo líquido produzida por `saldo_liquido` (R4.1).
COLUNA_SALDO_LIQUIDO = "saldo_liquido"

# Nome da coluna de saldo normalizado produzida por `saldo_por_10k` (R4.2).
COLUNA_SALDO_POR_10K = "saldo_por_10k"

# Chave_Municipal de 6 dígitos, comum ao CAGED cruzado e à Base_de_Municipios.
COLUNA_CHAVE_MUNICIPAL = "chave_municipal"

# Coluna de população estimada 2026 — denominador do Saldo_por_10k (R4.2).
# O nome segue exatamente o cabeçalho da Base_de_Municipios.
COLUNA_POPULACAO_2026 = "População estimada - pessoas [2026]"

# Fator de normalização do Saldo_por_10k (por 10.000 habitantes) (R4.2).
FATOR_POR_10K = 10_000


def saldo_liquido(df: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """Calcula o Saldo_Liquido por recorte como soma de `saldomovimentação` (R4.1).

    Agrupa o DataFrame pelas colunas declaradas em ``por`` (ex.:
    ``["chave_municipal", "seção", "competênciamov"]`` para o recorte município ×
    Secao_Industrial × mês) e soma a coluna `saldomovimentação`, cujos valores
    são ``+1`` para admissão e ``-1`` para desligamento. O resultado é, portanto,
    o balanço líquido de vínculos do recorte.

    Um grupo sem admissões nem desligamentos não aparece nos dados e, por
    construção, não gera linha; já um grupo cuja soma algébrica se anula resulta
    em saldo ``0``. Quando o DataFrame de entrada é vazio, o retorno é um
    DataFrame vazio com as colunas ``por + ["saldo_liquido"]`` — nenhum recorte
    existe, de modo que não há saldo a reportar (R4.10).

    Args:
        df: base cruzada/enriquecida contendo a coluna `saldomovimentação` e as
            colunas de recorte indicadas em ``por``. Não é modificada.
        por: lista não vazia de colunas que definem o recorte de agregação.

    Returns:
        Um DataFrame com uma linha por combinação distinta de ``por`` e a coluna
        ``saldo_liquido`` (``int``) com a soma de `saldomovimentação` do recorte.

    Raises:
        ValueError: se ``por`` for vazio.
        KeyError: se `saldomovimentação` ou alguma coluna de ``por`` estiver
            ausente no DataFrame.
    """
    if not por:
        raise ValueError("A lista de colunas de recorte 'por' não pode ser vazia.")

    faltando = [
        coluna
        for coluna in [*por, COLUNA_SALDO_MOVIMENTACAO]
        if coluna not in df.columns
    ]
    if faltando:
        raise KeyError(
            "Colunas ausentes no DataFrame para o cálculo de Saldo_Liquido: "
            f"{faltando}."
        )

    if df.empty:
        # Sem registros, não há recorte com saldo a reportar (R4.10).
        return pd.DataFrame(columns=[*por, COLUNA_SALDO_LIQUIDO])

    agregado = (
        df.groupby(por, dropna=False)[COLUNA_SALDO_MOVIMENTACAO]
        .sum()
        .reset_index()
        .rename(columns={COLUNA_SALDO_MOVIMENTACAO: COLUNA_SALDO_LIQUIDO})
    )
    return agregado


def _saldo_por_10k_valor(saldo: object, populacao: object) -> float:
    """Aplica a fórmula do Saldo_por_10k a um par (saldo, população) (R4.2, R4.3).

    Retorna ``(saldo / populacao) * 10_000`` quando a população é um número
    maior que zero (R4.2); retorna ``NaN`` quando a população está ausente
    (``NaN``/``None``) ou é zero/negativa (R4.3).
    """
    if populacao is None:
        return math.nan
    try:
        pop = float(populacao)
    except (TypeError, ValueError):
        return math.nan
    if math.isnan(pop) or pop <= 0:
        return math.nan
    return (float(saldo) / pop) * FATOR_POR_10K


def saldo_por_10k(saldo_df: pd.DataFrame, municipios: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o Saldo_Liquido pela população estimada 2026 (R4.2, R4.3).

    Combina o DataFrame de saldos (saída de `saldo_liquido`, que deve conter a
    coluna `chave_municipal` e `saldo_liquido`) com a Base_de_Municipios pela
    `chave_municipal`, e calcula, por recorte:

    ``saldo_por_10k = (saldo_liquido / populacao_2026) * 10_000``   se ``pop > 0``
    ``saldo_por_10k = NaN``                                          se ``pop``
    ausente ou ``<= 0``.

    A junção é à esquerda, preservando todas as linhas de ``saldo_df``;
    recortes cujo município não tem população conhecida na base recebem
    ``NaN`` (R4.3).

    Args:
        saldo_df: DataFrame de saldos por recorte, contendo ao menos as colunas
            ``chave_municipal`` e ``saldo_liquido``. Não é modificado.
        municipios: Base_de_Municipios tratada, contendo ``chave_municipal`` e a
            coluna de população estimada 2026. Não é modificada.

    Returns:
        Uma cópia de ``saldo_df`` acrescida da coluna ``saldo_por_10k``
        (``float`` ou ``NaN``).

    Raises:
        KeyError: se `chave_municipal` ou `saldo_liquido` faltar em ``saldo_df``,
            ou se `chave_municipal` ou a coluna de população faltar em
            ``municipios``.
    """
    faltando_saldo = [
        coluna
        for coluna in [COLUNA_CHAVE_MUNICIPAL, COLUNA_SALDO_LIQUIDO]
        if coluna not in saldo_df.columns
    ]
    if faltando_saldo:
        raise KeyError(
            "Colunas ausentes em 'saldo_df' para o Saldo_por_10k: "
            f"{faltando_saldo}."
        )

    faltando_mun = [
        coluna
        for coluna in [COLUNA_CHAVE_MUNICIPAL, COLUNA_POPULACAO_2026]
        if coluna not in municipios.columns
    ]
    if faltando_mun:
        raise KeyError(
            "Colunas ausentes em 'municipios' para o Saldo_por_10k: "
            f"{faltando_mun}."
        )

    resultado = saldo_df.copy()

    # Mapa chave_municipal → população estimada 2026 (uma linha por município).
    populacao = (
        municipios[[COLUNA_CHAVE_MUNICIPAL, COLUNA_POPULACAO_2026]]
        .drop_duplicates(subset=COLUNA_CHAVE_MUNICIPAL)
        .set_index(COLUNA_CHAVE_MUNICIPAL)[COLUNA_POPULACAO_2026]
    )

    pop_por_recorte = resultado[COLUNA_CHAVE_MUNICIPAL].map(populacao)

    resultado[COLUNA_SALDO_POR_10K] = [
        _saldo_por_10k_valor(saldo, pop)
        for saldo, pop in zip(
            resultado[COLUNA_SALDO_LIQUIDO], pop_por_recorte, strict=True
        )
    ]

    return resultado


def _coagir_estoque(valor: object) -> float:
    """Coage o estoque base para um número de forma robusta.

    O estoque pode chegar como número (ex.: ``120``/``120.0``), como texto
    numérico em formato brasileiro (ex.: ``"1.234,0"``) ou como rótulo de faixa
    decodificado pelo Limpador. Esta função extrai um valor numérico quando
    possível e devolve ``NaN`` caso contrário (R4.5), deixando a decisão de
    ausência a cargo de `turnover`.

    Regras de coerção:

    - ``None``/``NaN`` → ``NaN``.
    - Números (``int``/``float``) → o próprio valor em ``float``.
    - Texto: tenta converter diretamente; se falhar, normaliza o formato
      brasileiro (remove separador de milhar ``.`` e troca a vírgula decimal
      por ponto) e tenta novamente; se ainda assim não for numérico (rótulo de
      faixa sem número), devolve ``NaN``.
    """
    if valor is None:
        return math.nan
    if isinstance(valor, bool):
        # bool é subclasse de int; não representa um estoque válido.
        return math.nan
    if isinstance(valor, (int, float)):
        pop = float(valor)
        return math.nan if math.isnan(pop) else pop

    texto = str(valor).strip()
    if not texto:
        return math.nan
    try:
        return float(texto)
    except ValueError:
        pass
    normalizado = texto.replace(".", "").replace(",", ".")
    try:
        return float(normalizado)
    except ValueError:
        return math.nan


def _turnover_valor(admissoes: int, desligamentos: int, estoque: object) -> float:
    """Aplica a fórmula do Turnover a um recorte (R4.4, R4.5).

    ``turnover = min(admissoes, desligamentos) / estoque`` limitado a ``[0, 1]``
    quando o estoque base é um número maior que zero; ``NaN`` quando o estoque é
    ausente, zero ou negativo (R4.5).
    """
    estoque_num = _coagir_estoque(estoque)
    if math.isnan(estoque_num) or estoque_num <= 0:
        return math.nan
    bruto = min(admissoes, desligamentos) / estoque_num
    # Clamp em [0, 1]: admissoes/desligamentos são contagens >= 0, então o piso 0
    # é garantido; o teto 1 cobre o caso de fluxo maior que o estoque base (R4.4).
    if bruto < 0:
        return 0.0
    if bruto > 1:
        return 1.0
    return bruto


def turnover(df: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """Calcula o Turnover por recorte (R4.4, R4.5).

    Para cada recorte declarado em ``por`` (tipicamente
    ``["chave_municipal", "seção"]`` — município × Secao_Industrial), conta as
    admissões (``saldomovimentação == +1``) e os desligamentos
    (``saldomovimentação == -1``) e aplica:

    ``turnover = min(admissoes, desligamentos) / estoque_base``  limitado a
    ``[0, 1]`` quando o estoque base é maior que zero (R4.4);
    ``turnover = NaN``                                           quando o
    estoque base é zero ou ausente (R4.5).

    O estoque base (`estoque_base`, derivado da faixa `tamestabjan` pelo
    Limpador) é o denominador; o valor é coagido para número de forma robusta e
    recortes cujo estoque não é um número positivo recebem ``NaN``. Por recorte
    adota-se a **média** dos estoques observados no grupo, ignorando ausentes: o
    estoque é característica do estabelecimento, não do fluxo, e a média é o
    tamanho típico dos estabelecimentos que movimentaram no recorte.

    ponytail: o CAGED movimentado não traz identificador de estabelecimento, então
    não dá para somar estoques sem contar o mesmo estabelecimento várias vezes.
    A média da faixa é o melhor proxy disponível; trocar por estoque real se o
    RAIS entrar na base.

    Quando o DataFrame de entrada é vazio, o retorno é um DataFrame vazio com as
    colunas ``por + ["turnover"]``.

    Args:
        df: base cruzada/enriquecida contendo `saldomovimentação`, `estoque_base`
            e as colunas de recorte em ``por``. Não é modificada.
        por: lista não vazia de colunas que definem o recorte de agregação.

    Returns:
        Um DataFrame com uma linha por combinação distinta de ``por`` e a coluna
        ``turnover`` (``float`` em ``[0, 1]`` ou ``NaN``).

    Raises:
        ValueError: se ``por`` for vazio.
        KeyError: se `saldomovimentação`, `estoque_base` ou alguma coluna de
            ``por`` estiver ausente no DataFrame.
    """
    if not por:
        raise ValueError("A lista de colunas de recorte 'por' não pode ser vazia.")

    faltando = [
        coluna
        for coluna in [*por, COLUNA_SALDO_MOVIMENTACAO, COLUNA_ESTOQUE_BASE]
        if coluna not in df.columns
    ]
    if faltando:
        raise KeyError(
            "Colunas ausentes no DataFrame para o cálculo de Turnover: "
            f"{faltando}."
        )

    if df.empty:
        return pd.DataFrame(columns=[*por, COLUNA_TURNOVER])

    movimentacao = df[COLUNA_SALDO_MOVIMENTACAO]
    trabalho = df[[*por]].copy()
    trabalho["_admissao"] = (movimentacao == 1).astype(int)
    trabalho["_desligamento"] = (movimentacao == -1).astype(int)
    # Coage linha a linha antes de agregar, para que a média do recorte opere
    # sobre números (a coluna pode chegar como texto) e ignore os ausentes.
    trabalho["_estoque"] = df[COLUNA_ESTOQUE_BASE].map(_coagir_estoque).values

    agrupado = trabalho.groupby(por, dropna=False)
    agregado = agrupado.agg(
        _admissoes=("_admissao", "sum"),
        _desligamentos=("_desligamento", "sum"),
        _estoque=("_estoque", "mean"),
    ).reset_index()

    agregado[COLUNA_TURNOVER] = [
        _turnover_valor(int(adm), int(desl), estoque)
        for adm, desl, estoque in zip(
            agregado["_admissoes"],
            agregado["_desligamentos"],
            agregado["_estoque"],
            strict=True,
        )
    ]

    return agregado[[*por, COLUNA_TURNOVER]]


__all__ = [
    "COLUNA_SALDO_MOVIMENTACAO",
    "COLUNA_SALDO_LIQUIDO",
    "COLUNA_SALDO_POR_10K",
    "COLUNA_CHAVE_MUNICIPAL",
    "COLUNA_POPULACAO_2026",
    "COLUNA_ESTOQUE_BASE",
    "COLUNA_TURNOVER",
    "FATOR_POR_10K",
    "saldo_liquido",
    "saldo_por_10k",
    "turnover",
]


# ---------------------------------------------------------------------------
# Indice_de_Aquecimento (tarefa 7.7 — R4.8, R4.9)
# ---------------------------------------------------------------------------

# Coluna de competência mensal (formato AAAAMM) usada para ordenar a série e
# calcular a variação mês a mês do Saldo_Liquido (R4.8, R4.9).
COLUNA_COMPETENCIA = "competênciamov"

# Nome da coluna de variação mensal do Saldo_Liquido produzida internamente
# por `indice_aquecimento` (R4.8).
COLUNA_VARIACAO_MENSAL = "variacao_mensal"

# Nome da coluna de Indice_de_Aquecimento produzida por `indice_aquecimento` (R4.8).
COLUNA_INDICE_AQUECIMENTO = "indice_aquecimento"


def indice_aquecimento(saldo_mensal_df: pd.DataFrame) -> pd.DataFrame:
    """Calcula o Indice_de_Aquecimento por recorte e mês (R4.8, R4.9).

    O Indice_de_Aquecimento combina o nível relativo do saldo com o seu
    crescimento mês a mês::

        variacao_mensal        = Saldo_Liquido(mês) - Saldo_Liquido(mês anterior)
        variacao_mensal        = 0, se não há mês anterior na série do recorte (R4.9)
        Indice_de_Aquecimento  = Saldo_por_10k + variacao_mensal                 (R4.8)

    A variação é calculada **dentro de cada recorte**: as colunas de recorte são
    todas as colunas de ``saldo_mensal_df`` que não são a competência mensal
    (`competênciamov`) nem as métricas `saldo_liquido`/`saldo_por_10k`. Para cada
    recorte, a série é ordenada pela competência em ordem crescente e a
    `variacao_mensal` é a diferença de `saldo_liquido` em relação ao mês
    imediatamente anterior da série; o primeiro mês de cada recorte não tem mês
    anterior e, portanto, recebe variação ``0`` (R4.9).

    Quando o DataFrame de entrada é vazio, o retorno é um DataFrame vazio com as
    colunas originais acrescidas de ``variacao_mensal`` e ``indice_aquecimento``.

    Args:
        saldo_mensal_df: DataFrame mensal de saldos por recorte, saída de
            `saldo_por_10k` (após `saldo_liquido`), contendo ao menos as colunas
            `competênciamov`, `saldo_liquido` e `saldo_por_10k`, além das colunas
            de recorte. Não é modificado.

    Returns:
        Uma cópia de ``saldo_mensal_df`` acrescida das colunas
        ``variacao_mensal`` (``float``) e ``indice_aquecimento`` (``float``). A
        ordem das linhas é preservada em relação à entrada.

    Raises:
        KeyError: se `competênciamov`, `saldo_liquido` ou `saldo_por_10k`
            estiver ausente no DataFrame.
    """
    faltando = [
        coluna
        for coluna in [
            COLUNA_COMPETENCIA,
            COLUNA_SALDO_LIQUIDO,
            COLUNA_SALDO_POR_10K,
        ]
        if coluna not in saldo_mensal_df.columns
    ]
    if faltando:
        raise KeyError(
            "Colunas ausentes no DataFrame para o Indice_de_Aquecimento: "
            f"{faltando}."
        )

    if saldo_mensal_df.empty:
        # Sem séries mensais, não há variação nem índice a reportar (R4.9).
        vazio = saldo_mensal_df.copy()
        vazio[COLUNA_VARIACAO_MENSAL] = pd.Series(dtype="float64")
        vazio[COLUNA_INDICE_AQUECIMENTO] = pd.Series(dtype="float64")
        return vazio

    # O recorte é definido por todas as colunas que não são a competência mensal
    # nem as métricas de saldo — ex.: chave_municipal × Secao_Industrial.
    colunas_recorte = [
        coluna
        for coluna in saldo_mensal_df.columns
        if coluna
        not in {
            COLUNA_COMPETENCIA,
            COLUNA_SALDO_LIQUIDO,
            COLUNA_SALDO_POR_10K,
        }
    ]

    resultado = saldo_mensal_df.copy()

    # Ordena por recorte e competência para que o diff compare meses consecutivos
    # dentro da mesma série; preserva o índice original para restaurar a ordem.
    ordenado = resultado.sort_values(
        by=[*colunas_recorte, COLUNA_COMPETENCIA], kind="stable"
    )

    if colunas_recorte:
        variacao = ordenado.groupby(colunas_recorte, dropna=False)[
            COLUNA_SALDO_LIQUIDO
        ].diff()
    else:
        # Sem colunas de recorte, toda a entrada é uma única série mensal.
        variacao = ordenado[COLUNA_SALDO_LIQUIDO].diff()

    # O primeiro mês de cada recorte não tem mês anterior → variação 0 (R4.9).
    variacao = variacao.fillna(0.0)

    # Restaura a ordem original das linhas antes de anexar as colunas.
    variacao = variacao.reindex(resultado.index)

    resultado[COLUNA_VARIACAO_MENSAL] = variacao.astype("float64")
    resultado[COLUNA_INDICE_AQUECIMENTO] = (
        resultado[COLUNA_SALDO_POR_10K].astype("float64")
        + resultado[COLUNA_VARIACAO_MENSAL]
    )

    return resultado


__all__ += [
    "COLUNA_COMPETENCIA",
    "COLUNA_VARIACAO_MENSAL",
    "COLUNA_INDICE_AQUECIMENTO",
    "indice_aquecimento",
]


# ---------------------------------------------------------------------------
# Salário médio por movimentação e distribuição de escolaridade
# (tarefa 7.5 — R4.6, R4.7)
# ---------------------------------------------------------------------------

# Coluna de Secao_Industrial (seção CNAE) no CAGED cruzado (R4.6, R4.7).
COLUNA_SECAO = "seção"

# Coluna de salário (R$) do CAGED, já convertida para float pelo Limpador (R4.6).
COLUNA_SALARIO = "salário"

# Coluna de grau de instrução do CAGED, já decodificada pelo Limpador (R4.7).
COLUNA_GRAU_INSTRUCAO = "graudeinstrução"

# Códigos de movimentação: +1 admissão, -1 desligamento (R4.1).
SALDO_ADMISSAO = 1
SALDO_DESLIGAMENTO = -1

# Rótulos de movimentação usados nas tabelas de saída (R4.6, R4.7).
MOVIMENTACAO_ADMISSAO = "admissão"
MOVIMENTACAO_DESLIGAMENTO = "desligamento"

# Nomes das colunas produzidas por `salario_medio_por_movimentacao` (R4.6).
COLUNA_MOVIMENTACAO = "movimentação"
COLUNA_SALARIO_MEDIO = "salario_medio"

# Nomes das colunas produzidas por `distribuicao_escolaridade` (R4.7).
COLUNA_CONTAGEM = "contagem"
COLUNA_PROPORCAO = "proporção"

# Casas decimais do salário médio, em R$ (R4.6).
CASAS_DECIMAIS_SALARIO = 2

# Mapa código de movimentação → rótulo, restrito a admissão/desligamento.
_MOVIMENTACOES = {
    SALDO_ADMISSAO: MOVIMENTACAO_ADMISSAO,
    SALDO_DESLIGAMENTO: MOVIMENTACAO_DESLIGAMENTO,
}


def salario_medio_por_movimentacao(
    df: pd.DataFrame, por: list[str] | None = None
) -> pd.DataFrame:
    """Calcula o salário médio por movimentação e Secao_Industrial (R4.6).

    Separa os registros entre **admissão** (`saldomovimentação == +1`) e
    **desligamento** (`saldomovimentação == -1`) e, para cada combinação de
    movimentação × `seção`, calcula a média aritmética da coluna `salário`
    (em R$, arredondada a 2 casas decimais), **excluindo os valores ausentes**
    (``NaN``) do cálculo — comportamento padrão de ``mean`` do pandas.

    Registros cujo `saldomovimentação` não é ``+1`` nem ``-1`` são ignorados,
    pois não representam admissão nem desligamento. Um grupo em que todos os
    salários são ausentes resulta em média ``NaN`` (não há valor a promediar).

    Quando o DataFrame de entrada é vazio — ou não contém admissões nem
    desligamentos — o retorno é um DataFrame vazio com as colunas
    ``["movimentação", "seção", "salario_medio"]``.

    Args:
        df: base cruzada/enriquecida contendo as colunas `saldomovimentação`,
            `salário` e as colunas de recorte. Não é modificada.
        por: colunas que definem o recorte além da movimentação. O padrão é
            ``["seção"]`` (a leitura analítica por Secao_Industrial de R4.6); o
            Agregador passa o recorte completo do agregado para materializar o
            salário médio por município × seção × macrofamília × mês.

    Returns:
        Um DataFrame com uma linha por combinação de ``movimentação`` (rótulo
        ``"admissão"``/``"desligamento"``) e as colunas de ``por``, acrescido da
        coluna ``salario_medio`` (``float`` ou ``NaN``) com a média de `salário`.

    Raises:
        KeyError: se `saldomovimentação`, `seção` ou `salário` estiver ausente
            no DataFrame.
    """
    faltando = [
        coluna
        for coluna in [COLUNA_SALDO_MOVIMENTACAO, COLUNA_SECAO, COLUNA_SALARIO]
        if coluna not in df.columns
    ]
    if faltando:
        raise KeyError(
            "Colunas ausentes no DataFrame para o salário médio por "
            f"movimentação: {faltando}."
        )

    recorte_colunas = [COLUNA_SECAO] if por is None else list(por)
    colunas_saida = [COLUNA_MOVIMENTACAO, *recorte_colunas, COLUNA_SALARIO_MEDIO]

    faltando_recorte = [c for c in recorte_colunas if c not in df.columns]
    if faltando_recorte:
        raise KeyError(
            "Colunas de recorte ausentes para o salário médio por "
            f"movimentação: {faltando_recorte}."
        )

    # Mantém apenas admissões e desligamentos; demais movimentações são ignoradas.
    recorte = df[df[COLUNA_SALDO_MOVIMENTACAO].isin(_MOVIMENTACOES)].copy()

    if recorte.empty:
        return pd.DataFrame(columns=colunas_saida)

    recorte[COLUNA_MOVIMENTACAO] = recorte[COLUNA_SALDO_MOVIMENTACAO].map(_MOVIMENTACOES)

    # `mean` do pandas ignora NaN por padrão (R4.6: exclui ausentes da média).
    agregado = (
        recorte.groupby([COLUNA_MOVIMENTACAO, *recorte_colunas], dropna=False)[
            COLUNA_SALARIO
        ]
        .mean()
        .round(CASAS_DECIMAIS_SALARIO)
        .reset_index()
        .rename(columns={COLUNA_SALARIO: COLUNA_SALARIO_MEDIO})
    )
    return agregado[colunas_saida]


def distribuicao_escolaridade(df: pd.DataFrame) -> pd.DataFrame:
    """Distribui o grau de instrução entre admitidos e desligados por seção (R4.7).

    Para cada combinação de movimentação × `seção`, conta quantos registros há
    por `graudeinstrução` e calcula a proporção dentro do grupo (movimentação ×
    `seção`), de modo que as proporções de um mesmo grupo somem ``1``. Isso
    corresponde à distribuição (contagem/proporção) de escolaridade separada
    entre **admitidos** (`saldomovimentação == +1`) e **desligados**
    (`saldomovimentação == -1`).

    Registros cujo `saldomovimentação` não é ``+1`` nem ``-1`` são ignorados.
    Graus de instrução ausentes (``NaN``) **são preservados** como uma categoria
    própria na contagem (``dropna=False``), para que a soma das contagens iguale
    o total de registros do grupo.

    Quando o DataFrame de entrada é vazio — ou não contém admissões nem
    desligamentos — o retorno é um DataFrame vazio com as colunas
    ``["movimentação", "seção", "graudeinstrução", "contagem", "proporção"]``.

    Args:
        df: base cruzada/enriquecida contendo as colunas `saldomovimentação`,
            `seção` e `graudeinstrução`. Não é modificada.

    Returns:
        Um DataFrame com uma linha por combinação de ``movimentação``, ``seção``
        e ``graudeinstrução``, acrescido de ``contagem`` (``int``) e
        ``proporção`` (``float`` em ``[0, 1]`` dentro de cada movimentação ×
        seção).

    Raises:
        KeyError: se `saldomovimentação`, `seção` ou `graudeinstrução` estiver
            ausente no DataFrame.
    """
    faltando = [
        coluna
        for coluna in [COLUNA_SALDO_MOVIMENTACAO, COLUNA_SECAO, COLUNA_GRAU_INSTRUCAO]
        if coluna not in df.columns
    ]
    if faltando:
        raise KeyError(
            "Colunas ausentes no DataFrame para a distribuição de "
            f"escolaridade: {faltando}."
        )

    colunas_saida = [
        COLUNA_MOVIMENTACAO,
        COLUNA_SECAO,
        COLUNA_GRAU_INSTRUCAO,
        COLUNA_CONTAGEM,
        COLUNA_PROPORCAO,
    ]

    recorte = df[df[COLUNA_SALDO_MOVIMENTACAO].isin(_MOVIMENTACOES)].copy()

    if recorte.empty:
        return pd.DataFrame(columns=colunas_saida)

    recorte[COLUNA_MOVIMENTACAO] = recorte[COLUNA_SALDO_MOVIMENTACAO].map(_MOVIMENTACOES)

    # Contagem por (movimentação, seção, grau de instrução), preservando NaN de
    # escolaridade como categoria própria para que a soma iguale o total do grupo.
    contagem = (
        recorte.groupby(
            [COLUNA_MOVIMENTACAO, COLUNA_SECAO, COLUNA_GRAU_INSTRUCAO],
            dropna=False,
        )
        .size()
        .reset_index(name=COLUNA_CONTAGEM)
    )

    # Proporção dentro de cada grupo movimentação × seção (as proporções do
    # grupo somam 1 — R4.7).
    total_por_grupo = contagem.groupby(
        [COLUNA_MOVIMENTACAO, COLUNA_SECAO], dropna=False
    )[COLUNA_CONTAGEM].transform("sum")
    contagem[COLUNA_PROPORCAO] = contagem[COLUNA_CONTAGEM] / total_por_grupo

    return contagem[colunas_saida]


# Coluna ordinal de escolaridade derivada pelo Limpador (R4.7, R7.4).
COLUNA_ESCOLARIDADE_ORDINAL = "escolaridade_ordinal"

# Nome da coluna produzida por `escolaridade_media_por_movimentacao`.
COLUNA_ESCOLARIDADE_MEDIA = "escolaridade_media"


def escolaridade_media_por_movimentacao(
    df: pd.DataFrame, por: list[str] | None = None
) -> pd.DataFrame:
    """Calcula a escolaridade média por movimentação e recorte (R4.7).

    Irmã de `salario_medio_por_movimentacao`, sobre a coluna ordinal
    `escolaridade_ordinal` derivada pelo Limpador a partir de `graudeinstrução`.
    Enquanto `distribuicao_escolaridade` entrega a distribuição completa (a
    leitura analítica de R4.7), esta função entrega **um número por recorte** —
    que é o que a dispersão renda × escolaridade do dashboard precisa para ter
    um eixo contínuo (R7.4).

    Registros cujo `saldomovimentação` não é ``+1`` nem ``-1`` são ignorados;
    escolaridades ausentes são excluídas da média (comportamento padrão de
    ``mean``).

    Args:
        df: base contendo `saldomovimentação`, `escolaridade_ordinal` e as
            colunas de recorte. Não é modificada.
        por: colunas de recorte além da movimentação; padrão ``["seção"]``.

    Returns:
        Um DataFrame com ``movimentação``, as colunas de ``por`` e
        ``escolaridade_media`` (``float`` ou ``NaN``).

    Raises:
        KeyError: se `saldomovimentação`, `escolaridade_ordinal` ou alguma
            coluna de recorte estiver ausente.
    """
    recorte_colunas = [COLUNA_SECAO] if por is None else list(por)
    faltando = [
        coluna
        for coluna in [
            COLUNA_SALDO_MOVIMENTACAO,
            COLUNA_ESCOLARIDADE_ORDINAL,
            *recorte_colunas,
        ]
        if coluna not in df.columns
    ]
    if faltando:
        raise KeyError(
            f"Colunas ausentes para a escolaridade média: {faltando}."
        )

    colunas_saida = [COLUNA_MOVIMENTACAO, *recorte_colunas, COLUNA_ESCOLARIDADE_MEDIA]

    recorte = df[df[COLUNA_SALDO_MOVIMENTACAO].isin(_MOVIMENTACOES)].copy()
    if recorte.empty:
        return pd.DataFrame(columns=colunas_saida)

    recorte[COLUNA_MOVIMENTACAO] = recorte[COLUNA_SALDO_MOVIMENTACAO].map(_MOVIMENTACOES)

    agregado = (
        recorte.groupby([COLUNA_MOVIMENTACAO, *recorte_colunas], dropna=False)[
            COLUNA_ESCOLARIDADE_ORDINAL
        ]
        .mean()
        .reset_index()
        .rename(columns={COLUNA_ESCOLARIDADE_ORDINAL: COLUNA_ESCOLARIDADE_MEDIA})
    )
    return agregado[colunas_saida]


__all__ += [
    "COLUNA_SECAO",
    "COLUNA_SALARIO",
    "COLUNA_GRAU_INSTRUCAO",
    "SALDO_ADMISSAO",
    "SALDO_DESLIGAMENTO",
    "MOVIMENTACAO_ADMISSAO",
    "MOVIMENTACAO_DESLIGAMENTO",
    "COLUNA_MOVIMENTACAO",
    "COLUNA_SALARIO_MEDIO",
    "COLUNA_CONTAGEM",
    "COLUNA_PROPORCAO",
    "CASAS_DECIMAIS_SALARIO",
    "COLUNA_ESCOLARIDADE_ORDINAL",
    "COLUNA_ESCOLARIDADE_MEDIA",
    "salario_medio_por_movimentacao",
    "escolaridade_media_por_movimentacao",
    "distribuicao_escolaridade",
]
