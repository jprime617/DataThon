"""Dashboard interativo em Streamlit (R7).

Narrativa do painel: **localizar o problema → entender a causa raiz → decidir**.
O dashboard consome apenas as tabelas agregadas (poucos MB) geradas pelo
Agregador — nunca o CAGED bruto (R7.7, princípio "agregar antes de servir").

Este módulo começa pela fronteira de dados: `carregar_dados` resolve a origem
das tabelas agregadas com a estratégia de resiliência da demonstração (R9):

1. Tenta ler a tabela agregada do Blob_Storage (R9.2).
2. Em indisponibilidade do Blob, faz *fallback* para a cópia local em
   ``data_processed/caged_agregado.parquet`` (R9.6), para não bloquear o pitch.
3. Se **ambas** as origens estiverem indisponíveis, não levanta exceção: devolve
   um `ResultadoCarregamento` com ``disponivel=False`` e um `motivo`, de modo que
   o chamador exiba a mensagem de indisponibilidade e **se abstenha** de renderizar
   KPIs e gráficos (R7.8).

`carregar_dados` é mantida pura-ish (sem efeitos de Streamlit): recebe a leitura
do Blob como dependência injetável (`blob_loader`) para que os testes a exerçam
sem qualquer chamada de rede. O Streamlit é importado de forma tardia apenas na
camada fina de renderização (`main`), para que importar este módulo não exija um
servidor Streamlit em execução.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# `streamlit run dashboard/app.py` coloca no `sys.path` apenas a pasta do script
# (`dashboard/`), nunca a raiz do projeto — então `import src.*` falharia com
# `ModuleNotFoundError` embora funcione sob o pytest (que resolve a raiz pelo
# `conftest.py`). Resolvemos a raiz a partir deste arquivo, antes dos imports de
# `src`, para que o comando documentado no README funcione como está.
_RAIZ_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_PROJETO))

import pandas as pd

from src.agregador import (
    COLUNA_MACROFAMILIA_CBO,
    COLUNA_MES,
    COLUNA_MUNICIPIO,
    COLUNA_REGIAO,
    COLUNA_SALDO_LIQUIDO,
    COLUNA_SALDO_POR_10K,
    COLUNA_SECAO_INDUSTRIAL,
    COLUNA_TURNOVER,
)
from src.logging_pipeline import log_etapa, obter_logger

# Nome da etapa usado nas mensagens de log (coerente com R8.4).
_ETAPA = "dashboard"

# Caminho padrão da cópia local das tabelas agregadas, usada como fallback
# quando o Blob_Storage está indisponível (R9.6). `_RAIZ_PROJETO` é resolvida no
# topo do módulo, junto do ajuste de `sys.path`.
_CAMINHO_LOCAL_PADRAO = _RAIZ_PROJETO / "data_processed" / "caged_agregado.parquet"

# Variável de ambiente que guarda a credencial de acesso ao Azure (R8.5b),
# reutilizada do contrato do upload para manter a leitura do Blob consistente.
VAR_CREDENCIAL_AZURE = "AZURE_STORAGE_CONNECTION_STRING"

# Nome do blob da tabela agregada no Blob_Storage (R9.1/R9.2).
NOME_BLOB_AGREGADO = "caged_agregado.parquet"

# Variável de ambiente e padrão do container de destino no Blob_Storage. **O
# mesmo contrato usado pelo notebook no upload** (R9.1): com nomes divergentes
# dos dois lados, o dashboard não encontraria o blob e cairia no fallback local
# silenciosamente, deixando R9.2 sem exercício.
VAR_CONTAINER_AZURE = "AZURE_BLOB_CONTAINER"
CONTAINER_PADRAO = "caged-agregado"


def container_agregados(
    env: "os._Environ[str] | dict[str, str] | None" = None,
) -> str:
    """Nome do container das tabelas agregadas, de `AZURE_BLOB_CONTAINER`."""
    ambiente = os.environ if env is None else env
    return (ambiente.get(VAR_CONTAINER_AZURE) or "").strip() or CONTAINER_PADRAO

# Assinatura de uma função que lê a tabela agregada do Blob_Storage. Recebe a
# credencial de acesso ao Azure e devolve o DataFrame agregado. Abstrai o SDK
# `azure-storage-blob` para que `carregar_dados` seja testável sem rede.
CarregadorBlob = Callable[[str], pd.DataFrame]


@dataclass(frozen=True)
class ResultadoCarregamento:
    """Resultado da resolução da origem das tabelas agregadas (R7.7, R7.8, R9).

    Encapsula dados e status para que a camada de renderização decida, sem
    exceções, entre desenhar os KPIs/gráficos ou exibir indisponibilidade.

    Attributes:
        df: tabela agregada carregada; ``None`` quando indisponível.
        disponivel: ``True`` se os dados foram carregados do Blob_Storage ou do
            fallback local; ``False`` quando ambas as origens falharam (R7.8).
        origem: identifica de onde os dados vieram (``"blob"`` ou ``"local"``);
            ``None`` quando indisponível.
        motivo: mensagem legível descrevendo a indisponibilidade quando
            ``disponivel`` é ``False``; ``None`` em caso de sucesso (R7.8).
    """

    df: pd.DataFrame | None
    disponivel: bool
    origem: str | None = None
    motivo: str | None = None


def _carregar_blob_padrao(connection_string: str) -> pd.DataFrame:
    """Lê a tabela agregada do Blob_Storage usando o SDK do Azure (R9.2).

    Importa o SDK ``azure-storage-blob`` de forma tardia (dentro da função) para
    que o módulo possa ser importado e testado — com `blob_loader` injetado —
    mesmo em ambientes onde o SDK não esteja instalado. Baixa o blob da tabela
    agregada e o desserializa em um DataFrame a partir do conteúdo Parquet.
    """
    import io

    from azure.storage.blob import BlobServiceClient

    servico = BlobServiceClient.from_connection_string(connection_string)
    cliente_blob = servico.get_blob_client(
        container=container_agregados(), blob=NOME_BLOB_AGREGADO
    )
    conteudo = cliente_blob.download_blob().readall()
    return pd.read_parquet(io.BytesIO(conteudo))


def carregar_dados(
    *,
    blob_loader: CarregadorBlob | None = None,
    caminho_local: str | Path | None = None,
    env: "os._Environ[str] | dict[str, str] | None" = None,
) -> ResultadoCarregamento:
    """Resolve a origem das tabelas agregadas com fallback local (R7.7, R9).

    Estratégia de resiliência da demonstração (R9, princípio de design 5):

    1. **Blob_Storage primeiro** (R9.2): se houver credencial de acesso ao Azure
       no ambiente, tenta ler a tabela agregada via `blob_loader`. Em sucesso,
       devolve os dados com ``origem="blob"``.
    2. **Fallback local** (R9.6): se o Blob estiver indisponível (sem credencial
       ou erro de leitura), lê a cópia local em
       ``data_processed/caged_agregado.parquet``. Em sucesso, devolve os dados
       com ``origem="local"``.
    3. **Indisponibilidade** (R7.8): se **ambas** as origens falharem, **não**
       levanta exceção; devolve ``disponivel=False`` com um `motivo`, para que o
       chamador exiba a mensagem e se abstenha de renderizar KPIs/gráficos.

    A função não produz efeitos de Streamlit: é pura-ish e testável sem rede,
    pois a leitura do Blob é injetada por `blob_loader`.

    Args:
        blob_loader: função que lê a tabela agregada do Blob_Storage a partir da
            credencial; quando omitida, usa o leitor padrão baseado no SDK do
            Azure. Injetável nos testes para evitar rede.
        caminho_local: caminho da cópia local da tabela agregada; quando omitido,
            usa ``data_processed/caged_agregado.parquet``.
        env: mapeamento de variáveis de ambiente para localizar a credencial do
            Azure; usa ``os.environ`` quando omitido. Útil para testes.

    Returns:
        Um `ResultadoCarregamento` com os dados e o status de disponibilidade.
    """
    logger = obter_logger()
    ambiente = os.environ if env is None else env
    caminho = Path(caminho_local) if caminho_local is not None else _CAMINHO_LOCAL_PADRAO
    carregador = blob_loader or _carregar_blob_padrao

    motivos: list[str] = []

    # 1. Tenta o Blob_Storage primeiro (R9.2). Só aciona a leitura se houver
    #    credencial; sem ela, o Blob é considerado indisponível e segue ao
    #    fallback local, sem tratar isso como erro fatal.
    credencial = (ambiente.get(VAR_CREDENCIAL_AZURE) or "").strip()
    if credencial:
        try:
            df_blob = carregador(credencial)
            log_etapa(
                _ETAPA,
                f"tabela agregada carregada do Blob_Storage ({len(df_blob)} linhas).",
                logger=logger,
            )
            return ResultadoCarregamento(df=df_blob, disponivel=True, origem="blob")
        except Exception as exc:  # noqa: BLE001 — qualquer falha de Blob → fallback.
            motivos.append(f"Blob_Storage indisponível ({exc}).")
            logger.warning(
                "[%s] leitura do Blob_Storage falhou; tentando fallback local: %s",
                _ETAPA,
                exc,
            )
    else:
        motivos.append(
            f"Blob_Storage indisponível (credencial {VAR_CREDENCIAL_AZURE!r} "
            f"ausente ou vazia)."
        )

    # 2. Fallback para a cópia local (R9.6).
    try:
        df_local = pd.read_parquet(caminho)
        log_etapa(
            _ETAPA,
            (
                f"tabela agregada carregada da cópia local {str(caminho)!r} "
                f"({len(df_local)} linhas)."
            ),
            logger=logger,
        )
        return ResultadoCarregamento(df=df_local, disponivel=True, origem="local")
    except Exception as exc:  # noqa: BLE001 — falha de leitura local → indisponível.
        motivos.append(f"cópia local indisponível em {str(caminho)!r} ({exc}).")

    # 3. Ambas as origens falharam: sinaliza indisponibilidade sem levantar (R7.8).
    motivo = (
        "Dados agregados indisponíveis. "
        + " ".join(motivos)
        + " Os KPIs e gráficos não serão renderizados."
    )
    logger.error("[%s] %s", _ETAPA, motivo)
    return ResultadoCarregamento(
        df=None, disponivel=False, origem=None, motivo=motivo
    )


def _opcoes(df: pd.DataFrame, coluna: str) -> list:
    """Valores distintos e ordenados de uma coluna, para alimentar um filtro."""
    if coluna not in df.columns:
        return []
    return sorted(df[coluna].dropna().unique().tolist())


def _barra_lateral(df: pd.DataFrame) -> pd.DataFrame:
    """Desenha os filtros na barra lateral e devolve o subconjunto filtrado (R7.5).

    As quatro dimensões do painel — período, região, Secao_Industrial e
    Macrofamilia_CBO — viram seleções múltiplas alimentadas pelos valores
    presentes na própria tabela agregada. Seleção vazia significa "sem
    restrição", que é exatamente como `aplicar_filtros` interpreta uma coleção
    vazia: ao abrir, o painel mostra o retrato completo do estado.
    """
    import streamlit as st

    st.sidebar.header("Filtros")
    periodo = st.sidebar.multiselect("Período (AAAAMM)", _opcoes(df, COLUNA_MES))
    regiao = st.sidebar.multiselect("Município", _opcoes(df, COLUNA_REGIAO))
    secao = st.sidebar.multiselect(
        "Seção industrial", _opcoes(df, COLUNA_SECAO_INDUSTRIAL)
    )
    macrofamilia = st.sidebar.multiselect(
        "Macrofamília CBO", _opcoes(df, COLUNA_MACROFAMILIA_CBO)
    )
    st.sidebar.caption("Sem seleção = sem restrição naquela dimensão.")

    return aplicar_filtros(
        df,
        periodo=periodo,
        regiao=regiao,
        secao=secao,
        macrofamilia=macrofamilia,
    )


def main() -> None:
    """Ponto de entrada do dashboard Streamlit (camada fina de renderização).

    Importa o Streamlit de forma tardia para que importar este módulo não exija
    um servidor em execução. Carrega os dados e, em caso de indisponibilidade
    (R7.8), exibe a mensagem e **se abstém** de renderizar KPIs e gráficos.

    Com dados disponíveis, monta o painel na ordem da narrativa do design —
    *localizar o problema → entender a causa raiz → decidir*:

    1. filtros na barra lateral, que recalculam tudo o que vem abaixo (R7.5);
    2. os KPIs do recorte (R7.1), em zero quando o filtro não casa nada (R7.6);
    3. o mapa coroplético, que **localiza** onde está o apagão ou a expansão (R7.2);
    4. o ranking de seções, que diz **em que setor** o problema está (R7.3);
    5. a dispersão renda × escolaridade, que oferece a **causa raiz** (R7.4);
    6. a série temporal do saldo mensal, como leitura de tendência (bônus).
    """
    import streamlit as st

    st.set_page_config(
        page_title="Raio-X do Mercado de Trabalho — SC",
        page_icon="📊",
        layout="wide",
    )
    st.title("Raio-X do Mercado de Trabalho e Vagas Industriais em SC")

    resultado = carregar_dados()
    if not resultado.disponivel:
        st.error(resultado.motivo)
        return

    st.caption(
        f"Fonte dos dados: {resultado.origem} · "
        f"{len(resultado.df)} recortes (município × seção × macrofamília × mês)."
    )

    filtrado = _barra_lateral(resultado.df)

    render_kpis(filtrado)

    st.subheader("Onde está o gargalo")
    render_mapa(filtrado)

    st.subheader("Em que setor")
    render_ranking(filtrado)

    st.subheader("Por que: renda e escolaridade")
    render_dispersao(filtrado)

    st.subheader("Como evoluiu")
    render_serie_temporal(filtrado)


# ---------------------------------------------------------------------------
# Filtros e KPIs (tarefa 12.3 — R7.1, R7.5, R7.6)
# ---------------------------------------------------------------------------

# Rótulos legíveis dos KPIs exibidos no painel (R7.1). A ordem é a de exibição.
KPI_SALDO_LIQUIDO_TOTAL = "Saldo líquido total"
KPI_SALDO_POR_10K_MEDIO = "Saldo por 10k (médio)"
KPI_TURNOVER_MEDIO = "Turnover médio"


def aplicar_filtros(
    df: pd.DataFrame,
    periodo=None,
    regiao=None,
    secao=None,
    macrofamilia=None,
) -> pd.DataFrame:
    """Filtra a tabela agregada pelas dimensões do painel (R7.5).

    A narrativa do dashboard ("localizar → entender → decidir") exige que KPIs e
    gráficos reflitam **apenas** o subconjunto escolhido pelo usuário. Esta
    função pura aplica, em conjunção (``E`` lógico), os quatro filtros do painel
    sobre a tabela agregada produzida pelo Agregador:

    - ``periodo`` → coluna ``mes`` (competência AAAAMM);
    - ``regiao`` → coluna ``regiao`` (Chave_Municipal, identificador regional);
    - ``secao`` → coluna ``secao_industrial`` (Secao_Industrial);
    - ``macrofamilia`` → coluna ``macrofamilia_cbo`` (Macrofamilia_CBO).

    Cada filtro é **opcional**: um valor ``None`` — ou uma coleção vazia — não
    impõe restrição naquela dimensão (R7.5). Um valor escalar restringe a
    igualdade; uma coleção (lista/tupla/conjunto) restringe à pertença ao
    conjunto, permitindo seleção múltipla no painel. Nenhum filtro informado
    devolve a base inteira.

    A função é pura (não produz efeitos de Streamlit) e não modifica ``df``:
    retorna sempre uma cópia do subconjunto, preservando as colunas e a ordem
    das linhas remanescentes. Quando nenhum registro satisfaz os filtros, o
    retorno é um DataFrame vazio com o mesmo schema — base para os KPIs em zero
    (R7.6).

    Args:
        df: tabela agregada (saída do Agregador) a filtrar. Não é modificada.
        periodo: competência(s) AAAAMM a manter; ``None``/vazio = sem restrição.
        regiao: região(ões) (Chave_Municipal) a manter; ``None``/vazio = livre.
        secao: Secao_Industrial(is) a manter; ``None``/vazio = sem restrição.
        macrofamilia: Macrofamilia_CBO(s) a manter; ``None``/vazio = livre.

    Returns:
        Uma cópia de ``df`` contendo apenas as linhas que satisfazem **todos** os
        filtros informados. Mesmo schema de ``df``; possivelmente vazia.
    """
    mascara = pd.Series(True, index=df.index)
    for coluna, selecao in (
        (COLUNA_MES, periodo),
        (COLUNA_REGIAO, regiao),
        (COLUNA_SECAO_INDUSTRIAL, secao),
        (COLUNA_MACROFAMILIA_CBO, macrofamilia),
    ):
        mascara &= _mascara_dimensao(df, coluna, selecao)

    return df[mascara].copy()


def _mascara_dimensao(df: pd.DataFrame, coluna: str, selecao) -> pd.Series:
    """Constrói a máscara booleana de um filtro opcional sobre uma coluna (R7.5).

    Interpreta ``selecao`` de forma permissiva para servir à UI do painel:

    - ``None`` ou coleção vazia → sem restrição (máscara toda ``True``);
    - coleção (lista/tupla/conjunto/``Series``) → pertença ao conjunto;
    - escalar → igualdade.

    Se a ``coluna`` não existir no ``df``, trata como sem restrição para não
    quebrar o painel diante de um schema parcial.
    """
    if selecao is None or coluna not in df.columns:
        return pd.Series(True, index=df.index)

    if isinstance(selecao, (list, tuple, set, frozenset, pd.Series)):
        valores = list(selecao)
        if not valores:  # Coleção vazia = "sem restrição" (R7.5).
            return pd.Series(True, index=df.index)
        return df[coluna].isin(valores)

    return df[coluna] == selecao


def calcular_kpis(df: pd.DataFrame) -> list[tuple[str, float]]:
    """Calcula os KPIs do painel a partir do subconjunto filtrado (R7.1, R7.6).

    Deriva no mínimo 3 indicadores-chave das métricas de negócio do agregado,
    cada um com rótulo legível e valor numérico (R7.1):

    1. **Saldo líquido total** — soma de ``saldo_liquido`` no recorte;
    2. **Saldo por 10k (médio)** — média de ``saldo_por_10k``, ignorando ausentes;
    3. **Turnover médio** — média de ``turnover``, ignorando ausentes.

    Função pura e testável sem Streamlit: recebe o DataFrame já filtrado por
    :func:`aplicar_filtros` e devolve os pares ``(rótulo, valor)`` na ordem de
    exibição. Quando ``df`` é vazio — caso em que o filtro não casou com nenhum
    registro (R7.6) — **todos** os KPIs são ``0.0``, sem levantar exceção, para
    que o painel siga ativo exibindo zeros. Médias de colunas inteiramente
    ausentes também colapsam para ``0.0`` (em vez de ``NaN``), mantendo o
    contrato "rótulo + valor numérico".

    Args:
        df: subconjunto filtrado da tabela agregada. Não é modificado.

    Returns:
        Lista de pares ``(rótulo, valor)`` — ao menos 3 — na ordem de exibição.
    """
    return [
        (KPI_SALDO_LIQUIDO_TOTAL, _soma_segura(df, COLUNA_SALDO_LIQUIDO)),
        (KPI_SALDO_POR_10K_MEDIO, _media_segura(df, COLUNA_SALDO_POR_10K)),
        (KPI_TURNOVER_MEDIO, _media_segura(df, COLUNA_TURNOVER)),
    ]


def _soma_segura(df: pd.DataFrame, coluna: str) -> float:
    """Soma uma coluna numérica; 0.0 se vazia/ausente (R7.6)."""
    if df.empty or coluna not in df.columns:
        return 0.0
    total = pd.to_numeric(df[coluna], errors="coerce").sum()
    return float(total) if pd.notna(total) else 0.0


def _media_segura(df: pd.DataFrame, coluna: str) -> float:
    """Média de uma coluna ignorando ausentes; 0.0 se vazia/toda ausente (R7.6)."""
    if df.empty or coluna not in df.columns:
        return 0.0
    media = pd.to_numeric(df[coluna], errors="coerce").mean()
    return float(media) if pd.notna(media) else 0.0


def render_kpis(df: pd.DataFrame) -> None:
    """Exibe os KPIs no painel Streamlit (camada fina — R7.1, R7.6).

    Delega o cálculo à função pura :func:`calcular_kpis` e apenas desenha os
    pares ``(rótulo, valor)`` como métricas lado a lado. Importa o Streamlit de
    forma tardia para que importar este módulo (e testar `calcular_kpis`) não
    exija um servidor em execução. Com o filtro sem registros, mostra os KPIs em
    zero devolvidos por :func:`calcular_kpis`, sem encerrar o app (R7.6).

    Args:
        df: subconjunto filtrado da tabela agregada a resumir nos KPIs.
    """
    import streamlit as st

    kpis = calcular_kpis(df)
    colunas = st.columns(len(kpis))
    for coluna, (rotulo, valor) in zip(colunas, kpis):
        coluna.metric(label=rotulo, value=round(float(valor), 2))


# ---------------------------------------------------------------------------
# Visualizações (tarefa 12.5 — R7.2, R7.3, R7.4): mapa, ranking e dispersão
# ---------------------------------------------------------------------------
#
# Princípio de testabilidade: a lógica de construção de cada figura vive em uma
# função pura ``construir_*`` que RECEBE um DataFrame (e, quando aplicável, o
# GeoJSON) e RETORNA um ``plotly.graph_objects.Figure`` — sem importar Streamlit
# nem tocar em disco/rede. As funções ``render_*`` são a casca fina: resolvem a
# dependência de I/O (ler o GeoJSON), chamam a função pura e passam a figura para
# ``st.plotly_chart``. Assim os testes exercitam a lógica das visualizações sem
# um servidor Streamlit e sem artefatos externos.

# Caminho padrão da malha de municípios de SC usada no mapa coroplético (R7.2).
_CAMINHO_GEOJSON_PADRAO = _RAIZ_PROJETO / "dashboard" / "geo" / "sc_municipios.geojson"

# Chave de 6 dígitos do município dentro das *features* do GeoJSON. A malha deve
# expor essa propriedade para casar com a coluna `municipio` do agregado (derivada
# da Chave_Municipal de 6 dígitos — ver `agregador.py`).
CHAVE_GEOJSON = "chave_municipal"

# Escala divergente do mapa: negativos (apagão) em vermelho, zero em cinza-claro,
# positivos (expansão) em azul — valores negativos e positivos visualmente
# distinguíveis, como exige R7.2.
ESCALA_DIVERGENTE = [
    [0.0, "#b2182b"],  # mínimo (mais negativo) — apagão
    [0.5, "#f7f7f7"],  # ponto neutro (ancorado no zero via zmid)
    [1.0, "#2166ac"],  # máximo (mais positivo) — expansão
]

# Colunas que a dispersão renda × escolaridade consome, ambas emitidas pelo
# Agregador no mesmo recorte do agregado. A escolaridade é o nível **ordinal
# médio** dos admitidos (1 = Analfabeto … 11 = Doutorado), derivado do código de
# `graudeinstrução` pelo Limpador: um eixo contínuo permite a dispersão que R7.4
# pede, o que o rótulo textual da escolaridade não permitiria.
COLUNA_SALARIO_MEDIO_ADMISSAO = "salario_medio_admissao"
COLUNA_GRAU_INSTRUCAO = "escolaridade_media"


def _figura_vazia(mensagem: str):
    """Constrói uma figura Plotly de *empty-state* com uma anotação central.

    Usada quando não há dados suficientes para desenhar a visualização (filtro
    sem registros — R7.6 — ou dependência ausente, como o GeoJSON do mapa ou as
    colunas de salário/escolaridade na dispersão). Retorna uma figura válida e
    renderizável em vez de levantar exceção, para que o app siga sem encerrar.
    """
    import plotly.graph_objects as go

    figura = go.Figure()
    figura.update_layout(
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": mensagem,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 14},
            }
        ],
    )
    return figura


def construir_mapa(df: pd.DataFrame, geojson: dict | None):
    """Constrói o mapa coroplético de SC por `saldo_por_10k` (R7.2) — função pura.

    Colore cada município pelo ``saldo_por_10k`` agregado no município, usando uma
    **escala divergente** ancorada no zero (``zmid=0``), de modo que apagão
    (negativo) e expansão (positivo) fiquem visualmente distinguíveis. A legenda
    (barra de cores) é rotulada e expõe os limites mínimo e máximo da escala, que
    são fixados em ``zmin``/``zmax`` pelos extremos observados no recorte.

    O ``saldo_por_10k`` é agregado por município (soma entre seções/macrofamílias/
    meses do recorte filtrado) para produzir **um valor por município**, que é a
    unidade geográfica do mapa. Linhas com ``saldo_por_10k`` ausente são ignoradas
    na agregação.

    Degrada graciosamente (R7.6, dependência ausente): retorna uma figura de
    *empty-state* — em vez de quebrar — quando ``geojson`` é ``None`` (malha
    ausente), quando o DataFrame está vazio, quando faltam as colunas necessárias
    ou quando não sobra nenhum valor de ``saldo_por_10k`` após remover ausentes.

    Args:
        df: subconjunto (já filtrado) das tabelas agregadas, contendo ao menos as
            colunas ``municipio`` (chave de 6 dígitos) e ``saldo_por_10k``.
        geojson: malha GeoJSON dos municípios de SC, com a propriedade
            ``chave_municipal`` em cada *feature*; ``None`` quando a malha não está
            disponível.

    Returns:
        Uma ``plotly.graph_objects.Figure``: o coroplético quando há dados e malha,
        ou uma figura de *empty-state* com mensagem explicativa caso contrário.
    """
    import plotly.graph_objects as go

    if geojson is None:
        return _figura_vazia(
            "Mapa indisponível: malha de municípios "
            f"('{_CAMINHO_GEOJSON_PADRAO.name}') não encontrada."
        )

    colunas_necessarias = {COLUNA_MUNICIPIO, COLUNA_SALDO_POR_10K}
    if df.empty or not colunas_necessarias.issubset(df.columns):
        return _figura_vazia("Sem dados para o mapa no filtro selecionado.")

    # Um valor por município: soma o saldo por 10k entre os recortes filtrados,
    # ignorando ausentes (R4.3). Municípios sem nenhum valor saem da agregação.
    por_municipio = (
        df[[COLUNA_MUNICIPIO, COLUNA_SALDO_POR_10K]]
        .dropna(subset=[COLUNA_SALDO_POR_10K])
        .groupby(COLUNA_MUNICIPIO, as_index=False)[COLUNA_SALDO_POR_10K]
        .sum()
    )
    if por_municipio.empty:
        return _figura_vazia("Sem dados para o mapa no filtro selecionado.")

    valores = por_municipio[COLUNA_SALDO_POR_10K]
    minimo = float(valores.min())
    maximo = float(valores.max())

    figura = go.Figure(
        go.Choropleth(
            geojson=geojson,
            locations=por_municipio[COLUNA_MUNICIPIO].astype(str),
            z=valores,
            featureidkey=f"properties.{CHAVE_GEOJSON}",
            colorscale=ESCALA_DIVERGENTE,
            zmid=0,  # ancora o neutro no zero → divergência simétrica (R7.2).
            zmin=minimo,
            zmax=maximo,
            marker_line_width=0.3,
            marker_line_color="white",
            colorbar={
                # Legenda com os limites mínimo e máximo da escala (R7.2).
                "title": {"text": "Saldo por 10k hab."},
                "tickvals": [minimo, 0, maximo],
                "ticktext": [f"{minimo:.2f} (mín)", "0", f"{maximo:.2f} (máx)"],
            },
        )
    )
    figura.update_geos(fitbounds="locations", visible=False)
    figura.update_layout(
        title="Saldo por 10 mil habitantes por município (SC)",
        margin={"r": 0, "t": 40, "l": 0, "b": 0},
    )
    return figura


def _carregar_geojson(caminho: str | Path | None) -> dict | None:
    """Lê a malha GeoJSON dos municípios de SC do disco (fronteira de I/O).

    Resolve o caminho padrão (``dashboard/geo/sc_municipios.geojson``) quando
    ``caminho`` é ``None`` e desserializa o arquivo em um ``dict``. Degrada
    graciosamente devolvendo ``None`` quando a malha não existe ou não pode ser
    lida/parseada — o chamador transforma isso em figura de *empty-state* (R7.6).
    """
    import json

    alvo = Path(caminho) if caminho is not None else _CAMINHO_GEOJSON_PADRAO
    try:
        with alvo.open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, ValueError):
        return None


def render_mapa(
    df: pd.DataFrame, geojson: dict | str | Path | None = None
) -> None:
    """Renderiza o mapa coroplético de SC no Streamlit (R7.2) — casca fina de I/O.

    Resolve a malha GeoJSON e delega a construção à função pura `construir_mapa`,
    exibindo a figura via ``st.plotly_chart``. O argumento ``geojson`` aceita:

    - ``None``: lê a malha padrão de ``dashboard/geo/sc_municipios.geojson``;
    - ``str``/``Path``: caminho de uma malha alternativa a ler;
    - ``dict``: a malha GeoJSON já carregada (usada diretamente).

    Quando a malha está ausente/ilegível, `construir_mapa` recebe ``None`` e
    produz uma figura de *empty-state*, de modo que o app não quebra (R7.6).

    Args:
        df: subconjunto (já filtrado) das tabelas agregadas.
        geojson: malha GeoJSON (dict), caminho para ela, ou ``None`` para o padrão.
    """
    import streamlit as st

    malha = geojson if isinstance(geojson, dict) else _carregar_geojson(geojson)
    st.plotly_chart(construir_mapa(df, malha), width="stretch")


def construir_ranking(df: pd.DataFrame):
    """Constrói o ranking de Secao_Industrial por `saldo_liquido` (R7.3) — pura.

    Agrega o ``saldo_liquido`` por ``secao_industrial`` (soma entre municípios,
    macrofamílias e meses do recorte filtrado) e ordena as seções de forma
    **decrescente** pelo saldo agregado. O ``turnover`` é agregado em paralelo
    pela **média** das linhas da seção (ignorando ausentes), já que é uma taxa em
    ``[0, 1]`` e somá-lo não teria sentido. Cada barra exibe o ``saldo_liquido`` da
    seção e anota o ``turnover`` médio associado (R7.3).

    Degrada graciosamente (R7.6): retorna figura de *empty-state* quando o
    DataFrame está vazio ou faltam as colunas necessárias.

    Args:
        df: subconjunto (já filtrado) das tabelas agregadas, com ao menos
            ``secao_industrial``, ``saldo_liquido`` e ``turnover``.

    Returns:
        Uma ``plotly.graph_objects.Figure`` de barras ordenadas, ou figura de
        *empty-state*.
    """
    import plotly.graph_objects as go

    colunas_necessarias = {
        COLUNA_SECAO_INDUSTRIAL,
        COLUNA_SALDO_LIQUIDO,
        COLUNA_TURNOVER,
    }
    if df.empty or not colunas_necessarias.issubset(df.columns):
        return _figura_vazia("Sem dados para o ranking no filtro selecionado.")

    por_secao = (
        df.groupby(COLUNA_SECAO_INDUSTRIAL, as_index=False)
        .agg(
            saldo_liquido=(COLUNA_SALDO_LIQUIDO, "sum"),
            turnover=(COLUNA_TURNOVER, "mean"),
        )
        # Ordena decrescentemente por saldo_liquido (R7.3).
        .sort_values(COLUNA_SALDO_LIQUIDO, ascending=False)
    )
    if por_secao.empty:
        return _figura_vazia("Sem dados para o ranking no filtro selecionado.")

    saldos = por_secao[COLUNA_SALDO_LIQUIDO]
    turnovers = por_secao[COLUNA_TURNOVER]

    figura = go.Figure(
        go.Bar(
            x=saldos,
            y=por_secao[COLUNA_SECAO_INDUSTRIAL].astype(str),
            orientation="h",
            text=[f"{s:.2f}" for s in saldos],
            textposition="auto",
            customdata=turnovers,
            hovertemplate=(
                "%{y}<br>saldo líquido: %{x:.2f}"
                "<br>turnover: %{customdata:.2f}<extra></extra>"
            ),
        )
    )
    figura.update_layout(
        title="Ranking de seções industriais por saldo líquido",
        xaxis_title="Saldo líquido",
        yaxis_title="Seção industrial",
        # Maior saldo no topo (eixo y categórico invertido pela ordenação).
        yaxis={"autorange": "reversed"},
        margin={"r": 10, "t": 40, "l": 10, "b": 10},
    )
    return figura


def render_ranking(df: pd.DataFrame) -> None:
    """Renderiza o ranking de seções no Streamlit (R7.3) — casca fina.

    Delega a `construir_ranking` e exibe a figura via ``st.plotly_chart``.

    Args:
        df: subconjunto (já filtrado) das tabelas agregadas.
    """
    import streamlit as st

    st.plotly_chart(construir_ranking(df), width="stretch")


def construir_dispersao(df: pd.DataFrame):
    """Constrói a dispersão salário × escolaridade segmentada (R7.4) — pura.

    Relaciona ``salario_medio_admissao`` (eixo Y) com ``graudeinstrução`` (eixo X),
    segmentando os pontos por ``macrofamilia_cbo`` quando disponível, ou por
    ``secao_industrial`` como alternativa (R7.4). Cada segmento vira uma série de
    pontos com cor própria, permitindo comparar o padrão renda × escolaridade
    entre setores/macrofamílias.

    Degrada graciosamente (R7.6 e dependência de dados): retorna figura de
    *empty-state* quando o DataFrame está vazio, quando faltam as colunas
    ``salario_medio_admissao``/``graudeinstrução`` (ver NOTA de dependência na
    definição de `COLUNA_SALARIO_MEDIO_ADMISSAO`) ou quando não há nenhuma linha
    com ambos os valores presentes.

    Args:
        df: subconjunto (já filtrado) das tabelas agregadas. Deve conter
            ``salario_medio_admissao`` e ``graudeinstrução`` para render efetivo;
            idealmente também ``macrofamilia_cbo`` ou ``secao_industrial`` para o
            segmento.

    Returns:
        Uma ``plotly.graph_objects.Figure`` de dispersão segmentada, ou figura de
        *empty-state*.
    """
    import plotly.graph_objects as go

    colunas_necessarias = {COLUNA_SALARIO_MEDIO_ADMISSAO, COLUNA_GRAU_INSTRUCAO}
    if df.empty or not colunas_necessarias.issubset(df.columns):
        return _figura_vazia(
            "Dispersão indisponível: as colunas 'salario_medio_admissao' e "
            "'escolaridade_media' não estão na tabela agregada."
        )

    # Escolhe a dimensão de segmentação: macrofamília tem prioridade (R7.4),
    # com fallback para seção; se nenhuma existir, usa um único segmento.
    if COLUNA_MACROFAMILIA_CBO in df.columns:
        coluna_segmento: str | None = COLUNA_MACROFAMILIA_CBO
    elif COLUNA_SECAO_INDUSTRIAL in df.columns:
        coluna_segmento = COLUNA_SECAO_INDUSTRIAL
    else:
        coluna_segmento = None

    # Mantém apenas linhas com ambos os eixos presentes.
    dados = df.dropna(
        subset=[COLUNA_SALARIO_MEDIO_ADMISSAO, COLUNA_GRAU_INSTRUCAO]
    )
    if dados.empty:
        return _figura_vazia("Sem dados para a dispersão no filtro selecionado.")

    figura = go.Figure()
    if coluna_segmento is None:
        figura.add_trace(
            go.Scatter(
                x=dados[COLUNA_GRAU_INSTRUCAO],
                y=dados[COLUNA_SALARIO_MEDIO_ADMISSAO],
                mode="markers",
                name="Todos",
            )
        )
    else:
        for segmento, grupo in dados.groupby(coluna_segmento):
            figura.add_trace(
                go.Scatter(
                    x=grupo[COLUNA_GRAU_INSTRUCAO],
                    y=grupo[COLUNA_SALARIO_MEDIO_ADMISSAO],
                    mode="markers",
                    name=str(segmento),
                )
            )

    figura.update_layout(
        title="Salário médio de admissão × grau de instrução",
        xaxis_title="Escolaridade média dos admitidos (nível)",
        yaxis_title="Salário médio de admissão (R$)",
        legend_title=(coluna_segmento or "segmento"),
        margin={"r": 10, "t": 40, "l": 10, "b": 10},
    )
    return figura


def render_dispersao(df: pd.DataFrame) -> None:
    """Renderiza a dispersão renda × escolaridade no Streamlit (R7.4) — casca fina.

    Delega a `construir_dispersao` e exibe a figura via ``st.plotly_chart``.

    Args:
        df: subconjunto (já filtrado) das tabelas agregadas.
    """
    import streamlit as st

    st.plotly_chart(construir_dispersao(df), width="stretch")


# ---------------------------------------------------------------------------
# Visualização bônus (tarefa 12.7 — R7.4): série temporal do saldo mensal
# ---------------------------------------------------------------------------
#
# Gráfico bônus (não exigido pela entrega mínima): uma linha do `saldo_liquido`
# ao longo do tempo (`mes`), que complementa a leitura "por município/seção" dos
# demais gráficos com a leitura temporal — para perceber aceleração/desaceleração
# do mercado de trabalho. Segue o mesmo princípio de testabilidade das demais
# visualizações: `construir_serie_temporal` é pura (recebe DataFrame, devolve uma
# Figure, sem Streamlit/I/O) e `render_serie_temporal` é a casca fina que importa
# o Streamlit de forma tardia e desenha a figura.


def construir_serie_temporal(df: pd.DataFrame):
    """Constrói a série temporal do saldo mensal (bônus — R7.4) — função pura.

    Desenha o ``saldo_liquido`` agregado por mês (``mes``, competência AAAAMM) como
    uma linha ordenada no tempo, oferecendo a leitura temporal do mercado de
    trabalho que complementa os cortes geográfico (mapa) e setorial (ranking).

    Quando o recorte traz uma dimensão de segmentação — ``secao_industrial`` ou,
    preferencialmente, ``macrofamilia_cbo`` —, a série é quebrada em uma linha por
    segmento (soma do ``saldo_liquido`` por segmento e mês), permitindo comparar a
    trajetória mensal entre setores/macrofamílias. Sem nenhuma dessas colunas,
    desenha uma única linha com o saldo mensal total do recorte.

    O saldo é somado entre as demais dimensões dentro de cada (segmento × mês);
    meses são ordenados crescentemente para a linha fazer sentido no tempo. Linhas
    com ``mes`` ou ``saldo_liquido`` ausentes são ignoradas na agregação.

    Degrada graciosamente (R7.6, dependência ausente): retorna uma figura de
    *empty-state* — em vez de quebrar — quando o DataFrame está vazio, quando
    faltam as colunas ``mes``/``saldo_liquido`` ou quando não sobra nenhuma linha
    após remover ausentes.

    Args:
        df: subconjunto (já filtrado) das tabelas agregadas, com ao menos as
            colunas ``mes`` e ``saldo_liquido``; opcionalmente ``macrofamilia_cbo``
            ou ``secao_industrial`` para segmentar as linhas. Não é modificado.

    Returns:
        Uma ``plotly.graph_objects.Figure`` com a(s) linha(s) do saldo mensal, ou
        uma figura de *empty-state* com mensagem explicativa caso contrário.
    """
    import plotly.graph_objects as go

    colunas_necessarias = {COLUNA_MES, COLUNA_SALDO_LIQUIDO}
    if df.empty or not colunas_necessarias.issubset(df.columns):
        return _figura_vazia(
            "Sem dados para a série temporal no filtro selecionado."
        )

    # Escolhe a dimensão de segmentação: macrofamília tem prioridade (R7.4), com
    # fallback para seção; sem nenhuma, desenha uma única linha de saldo total.
    if COLUNA_MACROFAMILIA_CBO in df.columns:
        coluna_segmento: str | None = COLUNA_MACROFAMILIA_CBO
    elif COLUNA_SECAO_INDUSTRIAL in df.columns:
        coluna_segmento = COLUNA_SECAO_INDUSTRIAL
    else:
        coluna_segmento = None

    # Mantém apenas linhas com mês e saldo presentes.
    dados = df.dropna(subset=[COLUNA_MES, COLUNA_SALDO_LIQUIDO])
    if dados.empty:
        return _figura_vazia(
            "Sem dados para a série temporal no filtro selecionado."
        )

    figura = go.Figure()
    if coluna_segmento is None:
        serie = (
            dados.groupby(COLUNA_MES, as_index=False)[COLUNA_SALDO_LIQUIDO]
            .sum()
            .sort_values(COLUNA_MES)
        )
        figura.add_trace(
            go.Scatter(
                x=serie[COLUNA_MES].astype(str),
                y=serie[COLUNA_SALDO_LIQUIDO],
                mode="lines+markers",
                name="Saldo total",
            )
        )
    else:
        agregado_segmento = (
            dados.groupby(
                [coluna_segmento, COLUNA_MES], as_index=False
            )[COLUNA_SALDO_LIQUIDO]
            .sum()
            .sort_values(COLUNA_MES)
        )
        for segmento, grupo in agregado_segmento.groupby(coluna_segmento):
            figura.add_trace(
                go.Scatter(
                    x=grupo[COLUNA_MES].astype(str),
                    y=grupo[COLUNA_SALDO_LIQUIDO],
                    mode="lines+markers",
                    name=str(segmento),
                )
            )

    figura.update_layout(
        title="Série temporal do saldo líquido mensal",
        xaxis_title="Mês (competência)",
        yaxis_title="Saldo líquido",
        legend_title=(coluna_segmento or "segmento"),
        margin={"r": 10, "t": 40, "l": 10, "b": 10},
    )
    return figura


def render_serie_temporal(df: pd.DataFrame) -> None:
    """Renderiza a série temporal do saldo mensal no Streamlit (bônus — R7.4).

    Casca fina de renderização: delega a construção à função pura
    `construir_serie_temporal` e exibe a figura via ``st.plotly_chart``. Importa o
    Streamlit de forma tardia para que importar este módulo (e testar a função
    pura) não exija um servidor em execução.

    Args:
        df: subconjunto (já filtrado) das tabelas agregadas.
    """
    import streamlit as st

    st.plotly_chart(construir_serie_temporal(df), width="stretch")


__all__ = [
    "VAR_CREDENCIAL_AZURE",
    "VAR_CONTAINER_AZURE",
    "CONTAINER_PADRAO",
    "container_agregados",
    "NOME_BLOB_AGREGADO",
    "CarregadorBlob",
    "ResultadoCarregamento",
    "carregar_dados",
    "KPI_SALDO_LIQUIDO_TOTAL",
    "KPI_SALDO_POR_10K_MEDIO",
    "KPI_TURNOVER_MEDIO",
    "aplicar_filtros",
    "calcular_kpis",
    "render_kpis",
    "CHAVE_GEOJSON",
    "ESCALA_DIVERGENTE",
    "COLUNA_SALARIO_MEDIO_ADMISSAO",
    "COLUNA_GRAU_INSTRUCAO",
    "construir_mapa",
    "render_mapa",
    "construir_ranking",
    "render_ranking",
    "construir_dispersao",
    "render_dispersao",
    "construir_serie_temporal",
    "render_serie_temporal",
    "main",
]


# O Streamlit executa este arquivo como script com `run_name="__main__"`, então o
# guard abaixo é o que de fato desenha o painel em `streamlit run dashboard/app.py`.
# Sem ele o módulo seria importado, as funções definidas, e nada renderizado.
if __name__ == "__main__":
    main()
