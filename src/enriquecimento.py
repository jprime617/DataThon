"""Junta_Relacional (R3): cruzamento relacional entre CAGED e municípios.

Este módulo normaliza as chaves municipais das duas bases para um identificador
comum de **6 dígitos numéricos** (`Chave_Municipal`) e, posteriormente, executa
o cruzamento (left join) preservando todo o CAGED válido.

O CAGED identifica municípios com **6 dígitos** (ex.: ``420890``); a
Base_de_Municipios usa o código IBGE de **7 dígitos** (ex.: ``4200051``), cujo
7º dígito é verificador. A chave comum são, portanto, os **6 primeiros dígitos**
do código IBGE. Códigos malformados (comprimento diferente do esperado ou não
numéricos) são rejeitados retornando ``None`` para que o registro possa ser
excluído da junção, com contagem por base (R3.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.erros import ErroDeValidacao
from src.logging_pipeline import log_etapa

# Comprimento canônico da Chave_Municipal usada como chave de junção (R3.1).
_DIGITOS_CHAVE = 6
# Comprimento esperado do código IBGE de município na Base_de_Municipios (R3.2).
_DIGITOS_IBGE = 7
# Coluna de código de município no CAGED (6 dígitos).
_COLUNA_MUNICIPIO_CAGED = "município"
# Coluna de código IBGE de município na Base_de_Municipios (7 dígitos).
_COLUNA_CODIGO_MUNICIPIOS = "Código"
# Nome da Chave_Municipal derivada, usada como chave comum da junção.
_COLUNA_CHAVE = "chave_municipal"
# Limiar acima do qual se emite o alerta de não correspondência (R3.5).
_LIMIAR_SEM_CORRESPONDENCIA = 0.01
# Nome da etapa usado nas mensagens de log do pipeline.
_ETAPA = "junção"


def _nome_base(coluna: object) -> str:
    """Reduz um nome de coluna ao seu nome base para fins de correspondência.

    O cabeçalho real da Base_de_Municipios (extraído do IBGE) sufixa os nomes
    das colunas com um marcador de unidade/período entre colchetes — a coluna
    de código IBGE chega como ``"Código [-]"``. Para casar com o nome canônico
    (``"Código"``), removemos um sufixo final entre colchetes (``" [-]"``,
    ``" [2026]"``, etc.) e espaços nas extremidades.
    """
    texto = str(coluna).strip()
    # Remove um único sufixo final do tipo " [...]" (unidade/período IBGE).
    abre = texto.rfind("[")
    if abre != -1 and texto.endswith("]"):
        texto = texto[:abre].strip()
    return texto


def resolver_coluna_codigo(df_municipios: pd.DataFrame) -> str:
    """Resolve, em tempo de execução, o nome real da coluna de código IBGE.

    Tolera as duas variantes de cabeçalho observadas na Base_de_Municipios: o
    nome canônico ``"Código"`` (usado pelos fixtures de teste) e a forma do
    arquivo real do IBGE, ``"Código [-]"`` — e, por extensão, qualquer sufixo
    final entre colchetes. Primeiro procura o nome canônico exato; na ausência,
    procura uma coluna cujo nome base (sem o sufixo entre colchetes) seja igual
    ao canônico.

    Args:
        df_municipios: Base_de_Municipios cujas colunas serão inspecionadas.

    Returns:
        O nome real da coluna de código IBGE presente em `df_municipios`.

    Raises:
        ErroDeValidacao: se nenhuma coluna de código municipal for encontrada,
            listando as colunas disponíveis para facilitar o diagnóstico.
    """
    colunas = list(df_municipios.columns)
    # Correspondência exata com o nome canônico (caminho dos fixtures).
    if _COLUNA_CODIGO_MUNICIPIOS in colunas:
        return _COLUNA_CODIGO_MUNICIPIOS
    # Correspondência pelo nome base, tolerando o sufixo " [-]" do IBGE.
    for coluna in colunas:
        if _nome_base(coluna) == _COLUNA_CODIGO_MUNICIPIOS:
            return coluna
    raise ErroDeValidacao(
        f"Coluna de código municipal ausente na Base_de_Municipios: "
        f"esperava {_COLUNA_CODIGO_MUNICIPIOS!r} (ou variante com sufixo, "
        f"ex.: 'Código [-]'). Colunas disponíveis: {colunas}."
    )


def _normalizar_para_texto(codigo: object) -> str | None:
    """Reduz um código municipal a uma cadeia de dígitos, ou ``None``.

    Aceita entradas como texto (``"420890"``) ou numéricas (``420890`` ou
    ``420890.0``, resultado comum de leituras com valores ausentes que forçam
    a coluna a ponto flutuante). Retorna a representação textual composta
    apenas por dígitos, ou ``None`` quando a entrada é ausente/vazia ou não
    representa um valor inteiro não negativo.
    """
    # Valores ausentes (None, NaN) nunca produzem chave válida.
    if codigo is None:
        return None
    if isinstance(codigo, float):
        # NaN e infinitos não representam um código; inteiros em float
        # (ex.: 420890.0) são aceitos descartando a parte fracionária nula.
        if pd.isna(codigo) or not codigo.is_integer():
            return None
        return str(int(codigo))
    if isinstance(codigo, int):
        # `bool` é subclasse de `int`; tratá-lo como código é um erro.
        if isinstance(codigo, bool) or codigo < 0:
            return None
        return str(codigo)

    texto = str(codigo).strip()
    if not texto:
        return None
    # Remove um sufixo decimal nulo remanescente de conversões textuais
    # (ex.: "420890.0" vindo de um CSV lido como float).
    if texto.endswith(".0") and texto[:-2].isdecimal():
        texto = texto[:-2]
    # `str.isdecimal()` (e não `str.isdigit()`) garante apenas dígitos de base
    # 10 [0-9]: caracteres Unicode como sobrescritos ("²") são "dígitos" para
    # `isdigit()` mas não representam um código municipal válido e quebrariam
    # `int()`/`zfill` adiante. R3.1/R3.2 exigem dígitos numéricos reais.
    if not texto.isdecimal():
        return None
    return texto


def chave_municipal_caged(codigo: str | int | float) -> str | None:
    """Normaliza o código de município do CAGED para a Chave_Municipal (R3.1).

    A chave resultante tem **exatamente 6 dígitos numéricos**. Códigos com
    menos de 6 dígitos são preenchidos à esquerda com zeros (``zfill(6)``),
    acomodando municípios cujo código perde o zero inicial ao ser lido como
    número. Retorna ``None`` quando o código é malformado — não numérico,
    ausente/vazio ou com mais de 6 dígitos (R3.6).

    Args:
        codigo: código municipal do CAGED, como texto ou número.

    Returns:
        A Chave_Municipal de 6 dígitos, ou ``None`` se o código é malformado.
    """
    texto = _normalizar_para_texto(codigo)
    if texto is None:
        return None
    # Códigos com mais de 6 dígitos não são códigos municipais válidos do CAGED.
    if len(texto) > _DIGITOS_CHAVE:
        return None
    chave = texto.zfill(_DIGITOS_CHAVE)
    return chave if len(chave) == _DIGITOS_CHAVE else None


def chave_municipal_ibge(codigo7: str | int | float) -> str | None:
    """Normaliza o código IBGE de 7 dígitos para a Chave_Municipal (R3.2).

    Usa os **6 primeiros dígitos** do código IBGE, descartando o 7º dígito
    verificador. O código de origem deve ter exatamente 7 dígitos numéricos;
    qualquer outro comprimento ou conteúdo não numérico é considerado
    malformado e retorna ``None`` (R3.6).

    Args:
        codigo7: código IBGE do município (7 dígitos), como texto ou número.

    Returns:
        A Chave_Municipal de 6 dígitos (os 6 primeiros do IBGE), ou ``None``
        se o código é malformado.
    """
    texto = _normalizar_para_texto(codigo7)
    if texto is None:
        return None
    # O código IBGE de município tem exatamente 7 dígitos (6 + verificador).
    if len(texto) != _DIGITOS_IBGE:
        return None
    return texto[:_DIGITOS_CHAVE]


@dataclass(frozen=True)
class JoinResult:
    """Resultado do cruzamento relacional CAGED × municípios (R3.3–R3.6).

    Carrega a base cruzada e as métricas de auditoria da junção, para que o
    orquestrador (notebook) possa registrar o progresso da etapa e inspecionar
    a qualidade do cruzamento.

    Attributes:
        df: base cruzada (left join) preservando todo o CAGED com chave válida;
            os indicadores municipais são ausentes (NaN) quando não há
            correspondência (R3.3).
        total_caged: total de registros lidos do CAGED, antes de qualquer
            exclusão — é o total que R3.4 manda registrar e o denominador da
            proporção do alerta de R3.5.
        total_caged_valido: registros do CAGED com chave municipal válida, isto
            é, os que efetivamente entraram na junção.
        sem_correspondencia: número de registros do CAGED (com chave válida)
            sem município correspondente na Base_de_Municipios (R3.4).
        excluidos_caged: registros do CAGED excluídos por chave malformada
            (R3.6).
        excluidos_municipios: registros da Base_de_Municipios excluídos por
            chave malformada (R3.6).
        alerta: ``True`` quando a proporção sem correspondência excede o limiar
            de 1%, caso em que ``codigos_nao_correspondidos`` é preenchido
            (R3.5).
        codigos_nao_correspondidos: mapa ``código do CAGED → contagem`` dos
            códigos municipais sem correspondência; só é populado quando
            ``alerta`` é ``True`` (R3.5).
    """

    df: pd.DataFrame
    total_caged: int
    total_caged_valido: int
    sem_correspondencia: int
    excluidos_caged: int
    excluidos_municipios: int
    alerta: bool = False
    codigos_nao_correspondidos: dict[str, int] = field(default_factory=dict)


def juntar(df_caged: pd.DataFrame, df_municipios: pd.DataFrame) -> JoinResult:
    """Cruza o CAGED com a Base_de_Municipios por `Chave_Municipal` (R3.3–R3.6).

    Normaliza as chaves municipais das duas bases para o identificador comum de
    6 dígitos (``chave_municipal``) com `chave_municipal_caged` e
    `chave_municipal_ibge`. Registros cujo código é malformado (chave ``None``)
    são **excluídos** da junção, com contagem por base (R3.6).

    Executa um **left join** preservando todos os registros do CAGED com chave
    válida; municípios sem correspondência recebem valores ausentes (NaN) nos
    indicadores (R3.3). Registra a quantidade de registros do CAGED sem
    correspondência e o total lido do CAGED (R3.4). Se a proporção sem
    correspondência exceder 1% desse total, emite um alerta listando os códigos
    municipais não correspondidos e a contagem por código (R3.5).

    Args:
        df_caged: CAGED limpo, com a coluna ``município`` (código de 6 dígitos).
        df_municipios: Base_de_Municipios, com a coluna de código IBGE de 7
            dígitos — ``Código`` ou a variante do arquivo real ``Código [-]``,
            resolvida por `resolver_coluna_codigo` — e os indicadores
            socioeconômicos.

    Returns:
        Um `JoinResult` com a base cruzada e as métricas de auditoria da junção.
    """
    # --- Normaliza as chaves e separa registros com chave malformada (R3.6) ---
    # A chave normalizada são sempre 6 dígitos (string) ou None; forçamos dtype
    # `object` em ambas as bases para que uma base vazia ou totalmente malformada
    # — cujo `map` produz uma coluna só de NaN inferida como float64 — não quebre
    # o `merge` por incompatibilidade de tipos entre as colunas de chave.
    caged = df_caged.copy(deep=False)
    # Total lido, antes de qualquer exclusão: é o que R3.4 manda registrar e o
    # denominador da proporção do alerta de R3.5. Usar o total pós-exclusão
    # encolheria o denominador e dispararia o alerta mais facilmente.
    total_caged = int(len(caged))
    caged[_COLUNA_CHAVE] = (
        caged[_COLUNA_MUNICIPIO_CAGED].map(chave_municipal_caged).astype("object")
    )
    mascara_caged_valida = caged[_COLUNA_CHAVE].notna()
    excluidos_caged = int((~mascara_caged_valida).sum())
    caged_valido = caged[mascara_caged_valida]

    municipios = df_municipios.copy()
    # Resolve o nome real da coluna de código em tempo de execução, tolerando o
    # cabeçalho do arquivo IBGE ("Código [-]") além do nome canônico ("Código").
    coluna_codigo = resolver_coluna_codigo(municipios)
    municipios[_COLUNA_CHAVE] = (
        municipios[coluna_codigo].map(chave_municipal_ibge).astype("object")
    )
    mascara_mun_valida = municipios[_COLUNA_CHAVE].notna()
    excluidos_municipios = int((~mascara_mun_valida).sum())
    municipios_valido = municipios[mascara_mun_valida]

    # --- Left join preservando todo o CAGED válido (R3.3) ---
    # `indicator` marca quais linhas do CAGED não acharam par, sem depender de
    # qual indicador municipal possa ser legitimamente ausente (NaN) na base.
    df_cruzado = caged_valido.merge(
        municipios_valido,
        how="left",
        on=_COLUNA_CHAVE,
        indicator="_corresp",
    )

    total_caged_valido = int(len(df_cruzado))
    sem_corresp_mask = df_cruzado["_corresp"] == "left_only"
    sem_correspondencia = int(sem_corresp_mask.sum())
    df_cruzado = df_cruzado.drop(columns="_corresp")

    log_etapa(
        _ETAPA,
        (
            f"{total_caged} registros lidos do CAGED "
            f"({total_caged_valido} com chave válida); "
            f"{sem_correspondencia} sem município correspondente; "
            f"excluídos por chave malformada: CAGED={excluidos_caged}, "
            f"municípios={excluidos_municipios}."
        ),
    )

    # --- Alerta de limiar de não correspondência (R3.5) ---
    alerta = (
        total_caged > 0
        and sem_correspondencia / total_caged > _LIMIAR_SEM_CORRESPONDENCIA
    )
    codigos_nao_correspondidos: dict[str, int] = {}
    if alerta:
        contagem = (
            df_cruzado.loc[sem_corresp_mask, _COLUNA_CHAVE]
            .value_counts()
            .to_dict()
        )
        codigos_nao_correspondidos = {str(k): int(v) for k, v in contagem.items()}
        proporcao = sem_correspondencia / total_caged
        log_etapa(
            _ETAPA,
            (
                f"ALERTA: {proporcao:.2%} dos registros do CAGED sem "
                f"correspondência (> 1%). Códigos não correspondidos "
                f"(código → contagem): {codigos_nao_correspondidos}."
            ),
        )

    return JoinResult(
        df=df_cruzado,
        total_caged=total_caged,
        total_caged_valido=total_caged_valido,
        sem_correspondencia=sem_correspondencia,
        excluidos_caged=excluidos_caged,
        excluidos_municipios=excluidos_municipios,
        alerta=alerta,
        codigos_nao_correspondidos=codigos_nao_correspondidos,
    )


# Alias privado mantido por compatibilidade com quem já importava o nome antigo.
# O nome público é `resolver_coluna_codigo`: o orquestrador precisa dela para
# derivar a Chave_Municipal na Base_de_Municipios antes da agregação.
_resolver_coluna_codigo = resolver_coluna_codigo

__all__ = [
    "JoinResult",
    "chave_municipal_caged",
    "chave_municipal_ibge",
    "resolver_coluna_codigo",
    "juntar",
]
