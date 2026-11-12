"""Classificador_de_CBO (R5): enriquecimento de CBOs via agrupamento por IA.

Este módulo prepara os códigos `cbo2002ocupação` para o agrupamento em
macrofamílias pelo LLM_Externo e realiza a classificação de cada lote.

Funções puras de preparação do conjunto de CBOs:

- `extrair_cbos(df)`: extrai os códigos CBO distintos presentes no CAGED,
  descartando valores nulos ou vazios (R5.1).
- `lotear(itens, tamanho)`: particiona a lista de códigos em lotes de no máximo
  100 códigos, disjuntos e cuja concatenação, na ordem, reproduz a lista
  original — base para enviar as requisições ao LLM_Externo em lotes (R5.3).

Montagem de prompt e chamada ao LLM_Externo (tarefa 8.3):

- `montar_prompt(lote)`: monta o prompt que fixa o conjunto fechado de
  macrofamílias e exige saída JSON `{cbo: macrofamilia}` (R5.2, R5.8).
- `classificar_lote(lote, client)`: chama o LLM_Externo (retry ≤3, timeout 60 s),
  valida a resposta contra `MACROFAMILIAS` e aplica o fallback `Não classificado`
  (R5.6, R5.7).
- `verificar_credencial_llm()`: guarda de credencial que lê `LLM_API_KEY` da
  variável de ambiente e interrompe *antes* de chamar a API se ausente/vazia
  (R8.5a, R8.6).

A consolidação/persistência do mapeamento e o merge na base são implementados em
etapa posterior (tarefa 8.5).
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd

from src.erros import ErroDeValidacao
from src.logging_pipeline import log_etapa, obter_logger
from src import mapeamentos
from src.mapeamentos import (
    FAMILIA_POR_PREFIXO_CBO,
    MACROFAMILIAS,
    NAO_CLASSIFICADO,
    NIVEIS_QUALIFICACAO,
    NIVEL_POR_GRANDE_GRUPO,
    PREFIXOS_LIDERANCA,
)

# Nome da coluna de código de ocupação no CAGED.
COLUNA_CBO = "cbo2002ocupação"

# Tamanho máximo de um lote de códigos enviado ao LLM_Externo (R5.3).
TAMANHO_LOTE = 100

# Nome da variável de ambiente que guarda a credencial do LLM_Externo (R8.5a).
VAR_CREDENCIAL_LLM = "LLM_API_KEY"

# Número máximo de tentativas por lote ao chamar o LLM_Externo (R5.7).
MAX_TENTATIVAS = 3

# Tempo máximo (em segundos) de espera por resposta do LLM_Externo (R5.7).
TIMEOUT_SEGUNDOS = 60

# Espera base (segundos) entre tentativas, dobrada a cada retry. Repetir na hora
# não ajuda contra a causa mais comum de falha transitória na camada gratuita —
# saturação do modelo (HTTP 503) —, que precisa de alguns segundos para passar.
ESPERA_BASE_RETRY = 2

# Conjunto fechado de macrofamílias válidas, para validação O(1) da resposta.
_MACROFAMILIAS_VALIDAS = frozenset(MACROFAMILIAS)

# Caminho padrão do CSV do mapeamento CBO → macrofamília (R5.4).
CAMINHO_CSV_PADRAO = "data_processed/cbo_macrofamilias.csv"

# Nome da coluna de macrofamília no mapeamento persistido e na base enriquecida.
COLUNA_MACROFAMILIA = "macrofamilia"

# Colunas acrescentadas ao mapeamento persistido (a de macrofamília mantém o
# nome, para não quebrar o merge nem o agregador).
COLUNA_DESCRICAO = "descricao"
COLUNA_NIVEL = "nivel_qualificacao"
COLUNA_LIDERANCA = "lideranca"
COLUNA_JUSTIFICATIVA = "justificativa"

# Rodada 2 de concordância: mesma classificação com a ordem embaralhada.
SEED_RODADA_2 = 2026

# Com o provedor `arquivo`, a rodada 2 é a classificação anterior (Gemini),
# guardada ao lado do CSV: reexecutar o mesmo arquivo daria 100% trivialmente.
NOME_CSV_REFERENCIA = "cbo_macrofamilias_gemini.csv"
NOTA_ARQUIVO = "classificação via chat; prompts e respostas em `ia_cbo/`"
NOME_CSV_DIVERGENCIAS = "cbo_divergencias.csv"

# Sufixo do arquivo irmão que guarda o prompt usado no agrupamento (R5.8).
_SUFIXO_PROMPT = ".prompt.txt"

# Sufixo do arquivo irmão com provedor, modelo e concordância da classificação.
_SUFIXO_META = ".meta.json"

# Nome da etapa usado nas mensagens de log do pipeline.
_ETAPA = "CBO/LLM"

# A partir desta proporção de `Não classificado`, o fallback deixa de ser um
# caso de borda e vira sinal de falha sistemática da etapa — ver `classificar_cbos`.
LIMIAR_ALERTA_NAO_CLASSIFICADO = 0.5

# Códigos HTTP que indicam um problema de **configuração**, não uma falha
# transitória: credencial inválida (401), sem permissão (403), modelo inexistente
# (404) e requisição recusada (400 — inclui "credit balance is too low"). Repetir
# não ajuda, e cair no fallback produziria um artefato sintaticamente válido e
# vazio de conteúdo. Ver `_falha_permanente`.
_STATUS_PERMANENTES = frozenset({400, 401, 403, 404})


@runtime_checkable
class ClienteLLM(Protocol):
    """Interface mínima de um cliente do LLM_Externo (R5.9).

    A abstração isola o pipeline do SDK concreto do provedor (OpenAI, Gemini,
    Anthropic), o que permite injetar um cliente simulado nos testes sem
    qualquer chamada de rede. A implementação concreta é responsável por aplicar
    o `timeout` por requisição e por levantar exceção em falha/estouro de tempo,
    deixando a política de retry e de fallback a cargo de `classificar_lote`.
    """

    def classificar(self, prompt: str, *, timeout: int) -> str:
        """Envia `prompt` ao LLM_Externo e retorna a resposta textual (JSON).

        Args:
            prompt: prompt de classificação montado por `montar_prompt`.
            timeout: tempo máximo de espera, em segundos, por esta requisição.

        Returns:
            A resposta do modelo como texto — espera-se um objeto JSON
            `{cbo: macrofamilia}`.

        Raises:
            Exception: em caso de falha de rede, erro do provedor ou estouro do
                tempo limite (`timeout`).
        """
        ...


# Modelo padrão do LLM_Externo usado no agrupamento de CBOs (R5.9).
MODELO_PADRAO = "claude-opus-5"

# Teto de tokens da resposta. Um lote de 100 códigos devolve um JSON curto, mas
# o modelo pensa antes de responder; folga suficiente para não truncar.
MAX_TOKENS_RESPOSTA = 8192


class ClienteClaude:
    """Adaptador do SDK Anthropic (Claude) para a interface `ClienteLLM` (R5.9).

    Isola o SDK concreto atrás de ``classificar(prompt, *, timeout) -> str``,
    de modo que `classificar_lote` não conheça o provedor. O agrupamento roda
    **localmente** durante o pipeline, via API externa — nunca no Azure OpenAI,
    indisponível na conta de estudante (R9.5).

    O SDK é importado de forma tardia (dentro de ``__init__``) para que este
    módulo continue importável sem o pacote `anthropic` instalado — importante
    porque o dashboard alcança `src.cbo_ia` pela cadeia de imports e não precisa
    do SDK para desenhar a tela.

    A política de retry e o fallback `Não classificado` ficam a cargo de
    `classificar_lote` (R5.7); aqui tratamos apenas o timeout por requisição.
    """

    def __init__(self, api_key: str, modelo: str = MODELO_PADRAO) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._modelo = modelo

    def classificar(self, prompt: str, *, timeout: int) -> str:
        """Envia o prompt ao Claude e devolve o texto da resposta.

        Percorre os blocos de conteúdo procurando o primeiro de tipo ``text``:
        a resposta pode começar com um bloco de raciocínio (*thinking*), que não
        possui o atributo ``.text`` — ler ``content[0].text`` cegamente quebraria.
        """
        resposta = self._client.messages.create(
            model=self._modelo,
            max_tokens=MAX_TOKENS_RESPOSTA,
            timeout=timeout,
            messages=[{"role": "user", "content": prompt}],
        )
        for bloco in resposta.content:
            if getattr(bloco, "type", None) == "text":
                return bloco.text or ""
        return ""



# Modelo padrão do Gemini. A camada gratuita atende bem esta etapa (23 lotes de
# ≤100 códigos), mas os modelos `flash` de ponta vivem saturados nela e
# respondem 503; o `flash-lite` é o que responde de forma consistente e tem
# qualidade de sobra para classificar código CBO em macrofamília.
# Para listar o que a sua chave alcança: `genai.Client(...).models.list()`.
MODELO_PADRAO_GEMINI = "gemini-3.1-flash-lite"


class ClienteGemini:
    """Adaptador do SDK Google Gen AI para a interface `ClienteLLM` (R5.9).

    Alternativa **gratuita** ao `ClienteClaude`: o Google AI Studio emite uma
    chave sem cartão de crédito e a camada gratuita do `gemini-flash` acomoda
    com folga os ~23 lotes desta etapa. O design já prevê o LLM_Externo como
    "OpenAI, Google Gemini ou Anthropic" — trocar de provedor é exatamente o que
    a abstração `ClienteLLM` existe para permitir.

    Como em `ClienteClaude`, o SDK é importado de forma tardia para que o módulo
    continue importável sem o pacote instalado, e a política de retry e o
    fallback `Não classificado` ficam a cargo de `classificar_lote` (R5.7).

    A resposta é pedida em JSON via `response_mime_type`, o que elimina o texto
    de enquadramento que o modelo às vezes acrescenta ao redor do objeto.
    """

    def __init__(self, api_key: str, modelo: str = MODELO_PADRAO_GEMINI) -> None:
        from google import genai

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._modelo = modelo

    def classificar(self, prompt: str, *, timeout: int) -> str:
        """Envia o prompt ao Gemini e devolve o texto da resposta (JSON).

        O timeout do SDK é expresso em **milissegundos** na configuração de
        requisição, daí a conversão a partir dos segundos do contrato.
        """
        from google.genai import types

        resposta = self._client.models.generate_content(
            model=self._modelo,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=timeout * 1000),
            ),
        )
        return resposta.text or ""


# Pasta com os prompts gerados e as respostas coladas da IA paga (via chat).
# Ancorada na raiz do projeto: o notebook roda com o diretório em `notebooks/`.
PASTA_IA_CBO = Path(__file__).resolve().parent.parent / "ia_cbo"

# Nome do modelo usado no chat, só para o registro em `.meta.json`.
VAR_MODELO_MANUAL = "LLM_MODELO_MANUAL"


class ClienteArquivo:
    """`ClienteLLM` que lê respostas já salvas, em vez de chamar uma API (M2.C1).

    A classificação foi feita colando `ia_cbo/prompts/lote_NN.txt` numa IA paga
    via chat e salvando cada resposta em `ia_cbo/respostas/lote_NN.json`
    (`ia_cbo/COMO_USAR.md`). No ``__init__`` todas as respostas são juntadas por
    código; ``classificar`` devolve o dicionário inteiro, porque
    `classificar_lote` já fica só com os códigos do lote que pediu.

    Raises:
        ErroDeValidacao: se algum prompt não tiver a resposta correspondente
            (lista os lotes faltantes) ou se uma resposta não tiver JSON válido.
    """

    def __init__(self, pasta: str | os.PathLike | None = None, modelo: str | None = None) -> None:
        raiz = Path(pasta) if pasta is not None else PASTA_IA_CBO
        prompts = sorted((raiz / "prompts").glob("lote_*.txt"))
        respostas = raiz / "respostas"
        faltantes = [p.stem for p in prompts if not (respostas / f"{p.stem}.json").is_file()]
        if faltantes:
            raise ErroDeValidacao(
                f"Faltam {len(faltantes)} resposta(s) em {respostas}: {', '.join(faltantes)}. "
                "Rode esses prompts na IA e salve o JSON como lote_NN.json (ia_cbo/COMO_USAR.md)."
            )
        self._mapeamento: dict[str, dict] = {}
        for arquivo in sorted(respostas.glob("lote_*.json")):
            lido = _extrair_mapeamento(arquivo.read_text(encoding="utf-8"))
            if not lido:
                raise ErroDeValidacao(
                    f"{arquivo} não tem um objeto JSON válido. Peça à IA para repetir só o JSON completo."
                )
            self._mapeamento.update(lido)
        self._modelo = modelo or "manual (chat)"

    def classificar(self, prompt: str, *, timeout: int) -> str:  # noqa: ARG002 - contrato ClienteLLM
        return json.dumps(self._mapeamento, ensure_ascii=False)


# Provedores de LLM_Externo suportados por `criar_cliente_llm`.
PROVEDOR_ANTHROPIC = "anthropic"
PROVEDOR_GEMINI = "gemini"
PROVEDOR_ARQUIVO = "arquivo"

# Variável de ambiente que escolhe o provedor; o padrão é o Gemini, que tem
# camada gratuita e portanto é o caminho que roda sem custo.
VAR_PROVEDOR_LLM = "LLM_PROVIDER"
PROVEDOR_PADRAO = PROVEDOR_GEMINI


def criar_cliente_llm(
    provedor: str | None = None,
    env: "os._Environ[str] | dict[str, str] | None" = None,
) -> ClienteLLM:
    """Constrói o cliente do LLM_Externo do provedor configurado (R5.9).

    Lê a credencial de ``LLM_API_KEY`` com a guarda de R8.6 (interrompe antes de
    qualquer chamada à API se ausente/vazia) e o provedor de ``LLM_PROVIDER``:

    - ``gemini`` (padrão) — Google AI Studio, camada gratuita;
    - ``anthropic`` — Claude, requer saldo na conta;
    - ``arquivo`` — respostas coladas da IA paga em ``ia_cbo/respostas/``; não
      exige ``LLM_API_KEY`` e o nome do modelo vem de ``LLM_MODELO_MANUAL``.

    Args:
        provedor: força um provedor, ignorando a variável de ambiente.
        env: mapeamento de variáveis de ambiente; usa ``os.environ`` quando
            omitido. Útil para testes.

    Returns:
        Um `ClienteLLM` pronto para ser passado a `classificar_cbos`.

    Raises:
        ErroDeValidacao: se a credencial estiver ausente/vazia (R8.6) ou se o
            provedor configurado não for reconhecido.
    """
    ambiente = os.environ if env is None else env
    escolhido = (
        provedor
        if provedor is not None
        else (ambiente.get(VAR_PROVEDOR_LLM) or PROVEDOR_PADRAO)
    ).strip().lower()
    if escolhido == PROVEDOR_ARQUIVO:
        return ClienteArquivo(modelo=ambiente.get(VAR_MODELO_MANUAL))
    credencial = verificar_credencial_llm(ambiente)

    if escolhido == PROVEDOR_GEMINI:
        return ClienteGemini(api_key=credencial)
    if escolhido == PROVEDOR_ANTHROPIC:
        return ClienteClaude(api_key=credencial)
    raise ErroDeValidacao(
        f"Provedor de LLM_Externo desconhecido: {escolhido!r}. "
        f"Valores aceitos em {VAR_PROVEDOR_LLM!r}: "
        f"{PROVEDOR_GEMINI!r} (gratuito), {PROVEDOR_ANTHROPIC!r} ou {PROVEDOR_ARQUIVO!r}."
    )


def verificar_credencial_llm(env: "os._Environ[str] | dict[str, str] | None" = None) -> str:
    """Valida a presença da credencial do LLM_Externo antes de qualquer chamada.

    Lê a variável de ambiente ``LLM_API_KEY`` (R8.5a) e interrompe a execução,
    levantando `ErroDeValidacao`, se ela estiver ausente ou vazia — garantindo
    que o pipeline falhe *antes* de chamar a API externa (R8.6).

    Args:
        env: mapeamento de variáveis de ambiente a consultar; usa
            ``os.environ`` quando omitido. Útil para testes.

    Returns:
        O valor da credencial (sem espaços ao redor).

    Raises:
        ErroDeValidacao: se ``LLM_API_KEY`` estiver ausente ou vazia.
    """
    ambiente = os.environ if env is None else env
    credencial = (ambiente.get(VAR_CREDENCIAL_LLM) or "").strip()
    if not credencial:
        raise ErroDeValidacao(
            f"Credencial do LLM_Externo não fornecida: a variável de ambiente "
            f"{VAR_CREDENCIAL_LLM!r} está ausente ou vazia. Defina-a antes de "
            f"executar o enriquecimento de CBOs."
        )
    return credencial


def _normalizar_cbo(valor: object) -> str | None:
    """Normaliza um código CBO para texto, ou ``None`` se nulo/vazio.

    Aceita entradas textuais (``"223505"``) ou numéricas (``223505`` ou
    ``223505.0``, comum quando a coluna é lida como ponto flutuante por conter
    valores ausentes). Retorna a representação textual sem espaços ao redor, ou
    ``None`` quando a entrada é ausente (``None``/``NaN``) ou vazia (R5.1).
    """
    if valor is None:
        return None
    if isinstance(valor, float):
        # NaN é descartado; inteiros em float (ex.: 223505.0) viram "223505".
        if pd.isna(valor):
            return None
        if valor.is_integer():
            return str(int(valor))
        return str(valor)
    if isinstance(valor, int):
        # `bool` é subclasse de `int`; não é um código CBO válido.
        if isinstance(valor, bool):
            return None
        return str(valor)

    texto = str(valor).strip()
    if not texto:
        return None
    # Remove um sufixo decimal nulo remanescente de conversões textuais
    # (ex.: "223505.0" vindo de um CSV lido como float).
    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]
    return texto


def extrair_cbos(df: pd.DataFrame) -> list[str]:
    """Extrai os códigos `cbo2002ocupação` distintos do CAGED (R5.1).

    Descarta valores nulos (``None``/``NaN``) e vazios, retornando cada código
    distinto exatamente uma vez. A ordem preserva a primeira ocorrência de cada
    código no DataFrame, mantendo o resultado determinístico para uma mesma
    entrada.

    Args:
        df: DataFrame do CAGED contendo a coluna `cbo2002ocupação`.

    Returns:
        Lista de códigos CBO distintos (como texto), sem nulos nem vazios.

    Raises:
        KeyError: se a coluna `cbo2002ocupação` não estiver presente no df.
    """
    if COLUNA_CBO not in df.columns:
        raise KeyError(
            f"Coluna {COLUNA_CBO!r} ausente no DataFrame do CAGED. "
            f"Colunas disponíveis: {list(df.columns)}"
        )

    distintos: list[str] = []
    vistos: set[str] = set()
    for valor in df[COLUNA_CBO]:
        codigo = _normalizar_cbo(valor)
        if codigo is None or codigo in vistos:
            continue
        vistos.add(codigo)
        distintos.append(codigo)
    return distintos


def lotear(itens: list[str], tamanho: int = TAMANHO_LOTE) -> list[list[str]]:
    """Particiona `itens` em lotes de no máximo `tamanho` elementos (R5.3).

    Os lotes são disjuntos e a concatenação de todos, na ordem, reproduz
    exatamente a lista `itens` original. Uma lista vazia produz nenhum lote.

    Args:
        itens: lista de códigos CBO a particionar.
        tamanho: tamanho máximo de cada lote (padrão: 100 — R5.3).

    Returns:
        Lista de lotes, cada um com no máximo `tamanho` itens.

    Raises:
        ValueError: se `tamanho` não for um inteiro positivo.
    """
    if tamanho <= 0:
        raise ValueError(f"O tamanho do lote deve ser positivo, recebido: {tamanho}")
    return [itens[i : i + tamanho] for i in range(0, len(itens), tamanho)]


def _cbo6(codigo: str) -> str:
    """Código com 6 dígitos: o grande grupo 0 chega sem o zero à esquerda."""
    return codigo.zfill(6)


def descricao_cbo(codigo: str) -> str:
    """Descrição oficial da ocupação (aba `cbo2002ocupação`), ou ``""``."""
    try:
        return mapeamentos.CBO_OCUPACAO.get(int(codigo), "")
    except ValueError:
        return ""


def nivel_cbo(codigo: str) -> str:
    """Nível derivado do grande grupo (1º dígito): 1/2 → Superior, 3 → Técnico,
    demais → Qualificado (regra C)."""
    return NIVEL_POR_GRANDE_GRUPO.get(_cbo6(codigo)[0], "Qualificado")


def familia_sugerida(codigo: str) -> str | None:
    """Família sugerida pelo prefixo mais longo da tabela de desempate (regra B)."""
    c = _cbo6(codigo)
    for n in (3, 2, 1):
        if c[:n] in FAMILIA_POR_PREFIXO_CBO:
            return FAMILIA_POR_PREFIXO_CBO[c[:n]]
    return None


def lideranca(codigo: str, descricao: str = "") -> bool:
    """Flag de liderança (regra D): grande grupo 1 ou título de chefia."""
    return _cbo6(codigo)[0] == "1" or descricao.strip().startswith(PREFIXOS_LIDERANCA)


_REGRAS_PROMPT = """REGRAS
A. A macrofamília é o OFÍCIO da ocupação, NUNCA o setor do empregador. Faxineiro em fábrica têxtil → Serviços de apoio e outros; costureiro → Têxtil em qualquer setor.
B. Use só o conjunto fechado abaixo. Desempate: a família sugerida pelo prefixo da CBO (já informada por código). Só fuja dela com justificativa.
   1. Operação de linha e processo: 781, 784, 74, 81, 82, 83, 86 (784205 Alimentador de linha, 784105 Embalador a mão, 862150 Operador de máquinas fixas)
   2. Metalmecânica e eletroeletrônica: 72, 73 (724315 Soldador, 724205 Montador de estruturas metálicas, 721215 Operador de máquinas-ferramenta)
   3. Construção civil e extração: 71 (717020 Servente de obras, 715210 Pedreiro, 715505 Carpinteiro)
   4. Têxtil, confecção, couro e calçados: 76 (763210 e 763215 Costureiro, 763125 Ajudante de confecção)
   5. Alimentos e bebidas: 84 (848520 Magarefe, 841484 Preparação de pescados, 841505 Laticínios)
   6. Madeira, móveis, cerâmica e vidro: 75, 77 (771105 Marceneiro, 774105 Montador de móveis, 752305 Ceramista)
   7. Manutenção e reparação: 91, 95, 99 (911305 Mecânico de manutenção, 951105 Eletricista de manutenção, 954125 Operador eletromecânico)
   8. Logística e transporte: 782, 783, 414, 342 (414105 Almoxarife, 782510 Motorista de caminhão, 414135 Expedidor)
   9. Engenharia, técnicos industriais e TI: grande grupo 2 de exatas, engenharia e TI; 30, 31, 39, 317 (391205 Inspetor de qualidade, 391125 Técnico de planejamento de produção, 317110 Programador)
   10. Administrativo e comercial: grande grupo 4 (exceto 414), 25, 35, 52 (411005 Auxiliar de escritório, 411010 Assistente administrativo, 521110 Vendedor)
   11. Serviços de apoio e outros: 51, saúde, educação, grande grupo 6 (agro), grande grupo 0 (514320 Faxineiro, 513505 Auxiliar de alimentação, 517330 Vigilante)
   Grande grupo 1 (dirigentes): a família da área que a pessoa dirige (142105 Gerente administrativo → Administrativo e comercial).
C. Nível de qualificação, só 4 valores ordinais: Básico < Qualificado < Técnico < Superior. O nivel_cbo informado vem do 1º dígito (1 e 2 → Superior; 3 → Técnico; demais → Qualificado). Confirme-o ou ajuste-o; ao divergir, a justificativa é obrigatória. Caso típico: rebaixar para Básico ocupações elementares (alimentador de linha, servente, embalador, faxineiro).
D. Liderança não é nível nem família: supervisor, mestre, encarregado, chefe, gerente e diretor ficam com a família e o nível do ofício que lideram (410105 Supervisor administrativo → Administrativo e comercial, Qualificado; 710205 Mestre de construção civil → Construção civil e extração)."""


def montar_prompt(lote: list[str]) -> str:
    """Monta o prompt de classificação dos CBOs de um lote (R5.2, R5.8).

    O prompt instrui o modelo a atuar como classificador ocupacional, fixa o
    **conjunto fechado** de macrofamílias (`MACROFAMILIAS`) e exige saída
    estruturada em JSON — um objeto que mapeia cada código CBO para exatamente
    uma macrofamília do conjunto, sem texto adicional. O modelo deve escolher
    ``Não classificado`` sempre que estiver incerto (R5.6). O prompt resultante é
    determinístico para um mesmo lote, de modo que possa ser persistido ao lado
    do mapeamento para auditoria (R5.8).

    Args:
        lote: lista de códigos CBO (texto) a classificar; no máximo
            `TAMANHO_LOTE` elementos (R5.3).

    Returns:
        O prompt completo como texto.
    """
    familias = "\n".join(f"- {familia}" for familia in MACROFAMILIAS)
    niveis = ", ".join(NIVEIS_QUALIFICACAO)
    codigos = "\n".join(
        f"{c} | {descricao_cbo(c) or 'sem descrição'} | {nivel_cbo(c)} | "
        f"{familia_sugerida(c) or 'sem sugestão'}"
        for c in lote
    )
    return (
        "Você é um classificador ocupacional especializado na Classificação "
        "Brasileira de Ocupações (CBO 2002).\n\n"
        "Classifique cada código CBO abaixo em EXATAMENTE UMA macrofamília "
        "pertencente ao conjunto fechado a seguir e em um nível de qualificação. "
        "Não invente macrofamílias nem níveis fora destes conjuntos; quando "
        f"estiver incerto sobre a família, atribua {NAO_CLASSIFICADO!r}.\n\n"
        f"{_REGRAS_PROMPT}\n\n"
        "Conjunto fechado de macrofamílias:\n"
        f"{familias}\n\n"
        f"Níveis válidos: {niveis}.\n\n"
        "Cada linha traz: código | descrição | nivel_cbo | família sugerida pelo prefixo.\n"
        "Códigos CBO a classificar:\n"
        f"{codigos}\n\n"
        "Responda SOMENTE com um objeto JSON válido, sem texto antes ou depois, "
        'no formato {"<cbo>": {"macrofamilia": "...", "nivel": "...", '
        '"justificativa": "..."}}. A justificativa é uma frase curta, obrigatória '
        "quando a família diverge da sugerida ou o nível diverge do nivel_cbo. "
        "Inclua exatamente uma entrada por código informado."
    )


def _extrair_mapeamento(resposta: str) -> dict[str, dict]:
    """Extrai o objeto JSON `{cbo: {macrofamilia, nivel, justificativa}}`.

    Tolera texto antes/depois do objeto, recortando do primeiro ``{`` ao último
    ``}``. Retorna um dicionário vazio quando a resposta não contém um objeto
    JSON válido — nesse caso o chamador aplica o fallback `Não classificado`.
    """
    if not isinstance(resposta, str):
        return {}
    inicio = resposta.find("{")
    fim = resposta.rfind("}")
    if inicio == -1 or fim == -1 or fim < inicio:
        return {}
    try:
        dados = json.loads(resposta[inicio : fim + 1])
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(dados, dict):
        return {}
    # Normaliza as chaves para texto; descarta entradas que não são objetos.
    return {str(k): v for k, v in dados.items() if isinstance(v, dict)}


def _validar(codigo: str, bruto: dict | None) -> dict[str, str]:
    """Valida uma entrada da IA contra os conjuntos fechados (R5.6).

    Família inválida/ausente → `Não classificado`; nível inválido/ausente →
    `nivel_cbo`. Sem justificativa, a IA não pode fugir da regra: família
    divergente da sugerida volta para a sugerida, nível divergente volta para o
    `nivel_cbo` (regras B e C).
    """
    bruto = bruto or {}
    sugerida, nivel_base = familia_sugerida(codigo), nivel_cbo(codigo)
    familia = bruto.get("macrofamilia")
    if familia not in _MACROFAMILIAS_VALIDAS:
        familia = NAO_CLASSIFICADO
    nivel = bruto.get("nivel")
    if nivel not in NIVEIS_QUALIFICACAO:
        nivel = nivel_base
    justificativa = bruto.get("justificativa")
    justificativa = justificativa.strip() if isinstance(justificativa, str) else ""
    if not justificativa:
        if sugerida and familia not in (sugerida, NAO_CLASSIFICADO):
            familia = sugerida
        nivel = nivel_base
    return {"macrofamilia": familia, "nivel": nivel, "justificativa": justificativa}


def _falha_permanente(exc: Exception) -> bool:
    """Diz se a exceção indica problema de configuração, não falha transitória.

    O retry de R5.7 existe para falhas passageiras — rede instável, estouro de
    tempo, indisponibilidade momentânea do provedor. Um erro de credencial, de
    permissão, de modelo inexistente ou de saldo insuficiente não melhora na
    terceira tentativa: repetir só atrasa, e o fallback `Não classificado`
    transformaria um erro de configuração num artefato silenciosamente vazio —
    exatamente o modo de falha que a guarda de credencial (R8.6) existe para
    evitar.

    A detecção é feita por *duck typing* sobre o atributo ``status_code`` que os
    SDKs HTTP expõem nas suas exceções, de modo que este módulo continue
    importável sem o SDK do provedor instalado.
    """
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status in _STATUS_PERMANENTES


def classificar_lote(lote: list[str], client: ClienteLLM) -> dict[str, dict[str, str]]:
    """Classifica um lote de CBOs chamando o LLM_Externo (R5.6, R5.7).

    Monta o prompt (`montar_prompt`), chama ``client.classificar`` com timeout de
    `TIMEOUT_SEGUNDOS` segundos e repete em até `MAX_TENTATIVAS` tentativas caso a
    requisição falhe ou estoure o tempo. Para cada código do lote:

    - se o modelo devolveu uma macrofamília pertencente a `MACROFAMILIAS`, ela é
      usada;
    - se a macrofamília estiver ausente na resposta ou fora do conjunto, o código
      recebe ``Não classificado`` (R5.6).

    Esgotadas as tentativas (todas falharam/estouraram), **todo** o lote recebe
    ``Não classificado`` e a falha é registrada em log (R5.7).

    Exceção a esse fluxo: falhas **permanentes** (credencial inválida, sem
    permissão, modelo inexistente, saldo insuficiente — ver `_falha_permanente`)
    levantam `ErroDeValidacao` imediatamente, sem retry e sem fallback. São
    problemas de configuração, e mascará-los produziria um mapeamento inteiro de
    ``Não classificado`` sem que nada no pipeline falhasse.

    O lote vazio produz um mapeamento vazio sem chamar o cliente.

    Args:
        lote: códigos CBO a classificar (texto).
        client: cliente do LLM_Externo (abstração `ClienteLLM`), injetável para
            testes.

    Returns:
        Dicionário `código → {macrofamilia, nivel, justificativa}`, com
        exatamente uma entrada por código do lote, família em `MACROFAMILIAS` e
        nível em `NIVEIS_QUALIFICACAO` (ver `_validar`).

    Raises:
        ErroDeValidacao: em falha permanente do LLM_Externo (configuração).
    """
    if not lote:
        return {}

    prompt = montar_prompt(lote)
    logger = obter_logger()

    ultima_falha: Exception | None = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resposta = client.classificar(prompt, timeout=TIMEOUT_SEGUNDOS)
        except Exception as exc:  # noqa: BLE001 - qualquer falha dispara retry
            if _falha_permanente(exc):
                # Problema de configuração: interrompe em vez de mascarar com o
                # fallback. A mensagem precisa dizer o que corrigir.
                raise ErroDeValidacao(
                    "O LLM_Externo recusou a requisição de forma definitiva "
                    f"(HTTP {getattr(exc, 'status_code', '?')}): {exc}\n"
                    "Isso não é uma falha transitória e repetir não resolve. "
                    "Verifique, no provedor: saldo/billing da conta, validade da "
                    f"credencial {VAR_CREDENCIAL_LLM!r} e se o modelo "
                    "configurado em `MODELO_PADRAO` ainda existe. O pipeline foi "
                    "interrompido antes de gravar um mapeamento vazio."
                ) from exc
            ultima_falha = exc
            logger.warning(
                "[CBO/LLM] tentativa %d/%d falhou para lote de %d código(s): %s",
                tentativa,
                MAX_TENTATIVAS,
                len(lote),
                exc,
            )
            if tentativa < MAX_TENTATIVAS:
                # Backoff exponencial antes da próxima tentativa; não espera
                # depois da última, que já vai para o fallback.
                time.sleep(ESPERA_BASE_RETRY * (2 ** (tentativa - 1)))
            continue

        mapeamento_bruto = _extrair_mapeamento(resposta)
        # Valida cada código contra os conjuntos fechados (R5.6).
        return {codigo: _validar(codigo, mapeamento_bruto.get(codigo)) for codigo in lote}

    # Todas as tentativas falharam/estouraram: lote inteiro → `Não classificado`
    # e registro da falha (R5.7).
    logger.error(
        "[CBO/LLM] esgotadas %d tentativas para lote de %d código(s); "
        "atribuindo %r a todos. Última falha: %s",
        MAX_TENTATIVAS,
        len(lote),
        NAO_CLASSIFICADO,
        ultima_falha,
    )
    return {codigo: _validar(codigo, None) for codigo in lote}


def _classificar_todos(cbos: list[str], client: ClienteLLM) -> dict[str, dict[str, str]]:
    """Classifica todos os códigos em lotes de ≤100 (R5.3)."""
    resultado: dict[str, dict[str, str]] = {}
    for lote in lotear(cbos):
        resultado.update(classificar_lote(lote, client))
    return resultado


@dataclass(frozen=True)
class ClassificacaoResult:
    """Resultado do enriquecimento de CBOs via agrupamento por IA (R5.4–R5.8).

    Carrega a base enriquecida com a coluna `Macrofamilia_CBO`, o mapeamento
    consolidado (uma linha por CBO) e as métricas de auditoria da etapa, para
    que o orquestrador (notebook) possa registrar o progresso e seguir para a
    agregação.

    Attributes:
        df_enriquecido: base cruzada com a coluna de macrofamília anexada por
            merge no código `cbo2002ocupação` (R5.5). Códigos sem
            correspondência no mapeamento recebem valor ausente (NaN).
        mapeamento: mapa ``código CBO → macrofamília`` consolidado, com
            exatamente uma entrada por código distinto (R5.4). Todos os valores
            pertencem a `MACROFAMILIAS`.
        sem_correspondencia: número de linhas da base cujo `cbo2002ocupação`
            não encontrou correspondência no mapeamento durante o merge (R5.5).
        caminho_csv: caminho do `cbo_macrofamilias.csv` gravado (R5.4).
        caminho_prompt: caminho do arquivo irmão que guarda o prompt usado no
            agrupamento (R5.8).
    """

    df_enriquecido: pd.DataFrame
    mapeamento: dict[str, str]
    sem_correspondencia: int
    caminho_csv: str
    caminho_prompt: str


def _persistir_mapeamento(
    detalhes: dict[str, dict[str, str]],
    prompt: str,
    destino_csv: str,
) -> tuple[str, str]:
    """Grava o mapeamento CBO → macrofamília e o prompt usado em disco.

    Persiste o mapeamento consolidado em `destino_csv` com as colunas
    ``cbo2002ocupação`` e ``macrofamilia`` — uma linha por código distinto
    (R5.4) — e grava o prompt empregado num arquivo irmão ``<csv>.prompt.txt``
    para auditoria (R5.8). As pastas intermediárias são criadas se faltarem.

    Returns:
        Par ``(caminho_csv, caminho_prompt)`` com os caminhos efetivamente
        gravados (como texto).
    """
    caminho_csv = Path(destino_csv)
    caminho_csv.parent.mkdir(parents=True, exist_ok=True)

    mapa_df = pd.DataFrame(
        [
            {
                COLUNA_CBO: c,
                COLUNA_DESCRICAO: descricao_cbo(c),
                COLUNA_MACROFAMILIA: d["macrofamilia"],
                COLUNA_NIVEL: d["nivel"],
                COLUNA_LIDERANCA: lideranca(c, descricao_cbo(c)),
                COLUNA_JUSTIFICATIVA: d["justificativa"],
            }
            for c, d in detalhes.items()
        ],
        columns=[COLUNA_CBO, COLUNA_DESCRICAO, COLUNA_MACROFAMILIA, COLUNA_NIVEL,
                 COLUNA_LIDERANCA, COLUNA_JUSTIFICATIVA],
    )
    mapa_df.to_csv(caminho_csv, index=False, encoding="utf-8")

    caminho_prompt = caminho_csv.with_name(caminho_csv.name + _SUFIXO_PROMPT)
    caminho_prompt.write_text(prompt, encoding="utf-8")

    return str(caminho_csv), str(caminho_prompt)


def _registrar_concordancia(
    r1: dict[str, dict[str, str]],
    r2: dict[str, dict[str, str]],
    volume: pd.Series,
    destino: Path,
    logger,
) -> dict[str, float]:
    """Loga a % de concordância (família e nível) e grava as divergências."""
    linhas = [
        {
            COLUNA_CBO: c,
            COLUNA_DESCRICAO: descricao_cbo(c),
            "movimentacoes": int(volume.get(c, 0)),
            "macrofamilia_r1": r1[c]["macrofamilia"],
            "macrofamilia_r2": r2[c]["macrofamilia"],
            "nivel_r1": r1[c]["nivel"],
            "nivel_r2": r2[c]["nivel"],
        }
        for c in r1
    ]
    df = pd.DataFrame(linhas, columns=[COLUNA_CBO, COLUNA_DESCRICAO, "movimentacoes",
                                       "macrofamilia_r1", "macrofamilia_r2",
                                       "nivel_r1", "nivel_r2"])
    igual_fam = df["macrofamilia_r1"] == df["macrofamilia_r2"]
    igual_niv = df["nivel_r1"] == df["nivel_r2"]
    df[~(igual_fam & igual_niv)].sort_values("movimentacoes", ascending=False).to_csv(
        destino, index=False, encoding="utf-8"
    )
    if len(df):
        log_etapa(
            _ETAPA,
            f"Concordância rodada 1 × 2: família {igual_fam.mean():.1%}, "
            f"nível {igual_niv.mean():.1%}; divergências em {str(destino)!r}.",
            logger=logger,
        )
    return {
        "concordancia_familia": float(igual_fam.mean()) if len(df) else 1.0,
        "concordancia_nivel": float(igual_niv.mean()) if len(df) else 1.0,
    }


def _ler_mapeamento(caminho: Path) -> dict[str, dict[str, str]]:
    """Lê um `cbo_macrofamilias*.csv` como `{código: {macrofamilia, nivel}}`."""
    mapa = pd.read_csv(caminho, dtype={COLUNA_CBO: str})
    return {
        _normalizar_cbo(c): {"macrofamilia": f, "nivel": n}
        for c, f, n in zip(mapa[COLUNA_CBO], mapa[COLUNA_MACROFAMILIA], mapa[COLUNA_NIVEL])
        if _normalizar_cbo(c)
    }


def aplicar_mapeamento(
    df: pd.DataFrame, caminho_csv: str = CAMINHO_CSV_PADRAO
) -> pd.DataFrame:
    """Anexa macrofamília e nível a partir de um `cbo_macrofamilias.csv` já gerado.

    Reaproveita a classificação persistida sem chamar o LLM_Externo de novo:
    mesma normalização de código e mesmo merge à esquerda de `classificar_cbos`.
    """
    mapa = pd.read_csv(caminho_csv, dtype={COLUNA_CBO: str})
    mapa[COLUNA_CBO] = mapa[COLUNA_CBO].map(_normalizar_cbo)
    chave = df[COLUNA_CBO].map(_normalizar_cbo)
    resultado = df.copy(deep=False)
    for coluna in (COLUNA_MACROFAMILIA, COLUNA_NIVEL):
        resultado[coluna] = chave.map(dict(zip(mapa[COLUNA_CBO], mapa[coluna])))
    return resultado


def classificar_cbos(
    df: pd.DataFrame,
    client: ClienteLLM,
    *,
    destino_csv: str = CAMINHO_CSV_PADRAO,
    env: "os._Environ[str] | dict[str, str] | None" = None,
    verificar_credencial: bool = True,
) -> ClassificacaoResult:
    """Consolida o mapeamento de CBOs, persiste-o e o combina à base (R5.4–R5.8).

    Orquestra a etapa de enriquecimento de CBOs:

    1. Valida a credencial do LLM_Externo *antes* de qualquer chamada à API,
       interrompendo com `ErroDeValidacao` se ausente/vazia (R8.5a, R8.6).
       A guarda pode ser desativada via ``verificar_credencial=False``
       (p. ex. em testes com cliente simulado).
    2. Extrai os CBOs distintos (`extrair_cbos`, R5.1) e os particiona em lotes
       de no máximo 100 (`lotear`, R5.3).
    3. Classifica cada lote (`classificar_lote`, R5.6/R5.7) e consolida o
       resultado num mapeamento com **exatamente uma entrada por CBO** (R5.4).
       Todos os valores pertencem a `MACROFAMILIAS`.
    4. Persiste o mapeamento em `cbo_macrofamilias.csv` e grava o prompt usado
       num arquivo irmão para auditoria (R5.4, R5.8).
    5. Combina a macrofamília à base pelo código `cbo2002ocupação` (merge à
       esquerda) e conta as linhas sem correspondência no mapeamento (R5.5).

    O agrupamento executa localmente durante o pipeline, via API externa (R5.9);
    `client` é injetável para isolar os testes de qualquer chamada de rede.

    Args:
        df: base cruzada (saída da Junta_Relacional) contendo a coluna
            `cbo2002ocupação`.
        client: cliente do LLM_Externo (abstração `ClienteLLM`), injetável.
        destino_csv: caminho do CSV do mapeamento a gravar (padrão:
            `data_processed/cbo_macrofamilias.csv`).
        env: mapeamento de variáveis de ambiente para a guarda de credencial;
            usa ``os.environ`` quando omitido. Útil para testes.
        verificar_credencial: quando ``True`` (padrão), executa a guarda de
            credencial antes de chamar o LLM_Externo (R8.6).

    Returns:
        Um `ClassificacaoResult` com a base enriquecida, o mapeamento
        consolidado, a contagem sem correspondência e os caminhos gravados.

    Raises:
        ErroDeValidacao: se a guarda estiver ativa e `LLM_API_KEY` estiver
            ausente ou vazia (R8.6).
        KeyError: se a coluna `cbo2002ocupação` não estiver presente em `df`.
    """
    # 1. Guarda de credencial antes de qualquer chamada à API externa (R8.6).
    # Respostas lidas de arquivo não chamam API nenhuma: não há credencial a exigir.
    if verificar_credencial and not isinstance(client, ClienteArquivo):
        verificar_credencial_llm(env)

    logger = obter_logger()

    # 2. Extrai CBOs distintos (R5.1) e particiona em lotes de ≤100 (R5.3).
    cbos = extrair_cbos(df)
    lotes = lotear(cbos)

    # 3. Classifica cada lote e consolida em 1 entrada por CBO (R5.4, R5.6/R5.7).
    detalhes = _classificar_todos(cbos, client)
    mapeamento = {c: d["macrofamilia"] for c, d in detalhes.items()}

    # 3b. Um fallback pontual é esperado (R5.6/R5.7); um fallback *generalizado*
    # significa que as chamadas não estão funcionando — modelo inexistente,
    # credencial sem crédito, rede bloqueada — e o pipeline terminaria com um
    # artefato sintaticamente válido e vazio de conteúdo. Torna isso visível.
    if cbos:
        nao_classificados = sum(
            1 for familia in mapeamento.values() if familia == NAO_CLASSIFICADO
        )
        proporcao = nao_classificados / len(cbos)
        if proporcao >= LIMIAR_ALERTA_NAO_CLASSIFICADO:
            logger.error(
                "[%s] ALERTA: %.1f%% dos CBOs (%d de %d) ficaram como %r. "
                "Verifique o modelo configurado, a credencial e a conectividade "
                "— o enriquecimento por IA não produziu classificação útil.",
                _ETAPA,
                proporcao * 100,
                nao_classificados,
                len(cbos),
                NAO_CLASSIFICADO,
            )

    # 4. Persiste o mapeamento e o prompt usado (R5.4, R5.8). O prompt é
    # determinístico para um dado conjunto de códigos; registramos o prompt
    # completo do conjunto distinto para auditoria.
    prompt_usado = montar_prompt(cbos)
    caminho_csv, caminho_prompt = _persistir_mapeamento(
        detalhes, prompt_usado, destino_csv
    )

    # 5. Merge da macrofamília na base pelo código `cbo2002ocupação` (R5.5).
    # Os códigos da base são normalizados da mesma forma que em `extrair_cbos`
    # para casar com as chaves do mapeamento (texto, sem sufixo decimal nulo).
    df_enriquecido = df.copy(deep=False)
    chave_normalizada = df_enriquecido[COLUNA_CBO].map(_normalizar_cbo)
    df_enriquecido[COLUNA_MACROFAMILIA] = chave_normalizada.map(mapeamento)
    df_enriquecido[COLUNA_NIVEL] = chave_normalizada.map(
        {c: d["nivel"] for c, d in detalhes.items()}
    )

    # CBOs sem correspondência no mapeamento: linhas cuja macrofamília ficou
    # ausente após o merge (inclui códigos nulos/vazios, que não entram no
    # mapeamento por construção).
    sem_correspondencia = int(df_enriquecido[COLUNA_MACROFAMILIA].isna().sum())

    # 6. Rodada 2. Por API: a mesma classificação com a ordem embaralhada
    # (lotes com vizinhança diferente). Por arquivo: a classificação anterior
    # (Gemini), já que reler as mesmas respostas daria 100%. Só mede a
    # estabilidade; o mapeamento final é sempre o da rodada 1.
    extras: dict[str, object] = {}
    referencia = Path(caminho_csv).with_name(NOME_CSV_REFERENCIA)
    if isinstance(client, ClienteArquivo) and referencia.is_file():
        rodada2 = _ler_mapeamento(referencia)
        comuns = {c: d for c, d in detalhes.items() if c in rodada2}
        extras = {
            "comparacao": f"IA paga (chat) × classificação anterior ({referencia.name})",
            "cbos_comparados": len(comuns),
            "nota": NOTA_ARQUIVO,
        }
        r1 = comuns
    else:
        embaralhados = list(cbos)
        random.Random(SEED_RODADA_2).shuffle(embaralhados)
        rodada2 = _classificar_todos(embaralhados, client)
        extras = {"comparacao": "mesma IA, 2ª rodada com a ordem dos códigos embaralhada"}
        if isinstance(client, ClienteArquivo):
            extras["nota"] = NOTA_ARQUIVO
        r1 = detalhes
    concordancia = _registrar_concordancia(
        r1, rodada2, chave_normalizada.value_counts(),
        Path(caminho_csv).with_name(NOME_CSV_DIVERGENCIAS), logger,
    )
    # Procedência da classificação, lida depois pelo `metadados.json`.
    Path(caminho_csv + _SUFIXO_META).write_text(
        json.dumps(
            {
                "provedor": type(client).__name__,
                "modelo": getattr(client, "_modelo", None),
                "gerado_em": pd.Timestamp.now().isoformat(timespec="seconds"),
                **concordancia,
                **extras,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    log_etapa(
        _ETAPA,
        (
            f"{len(cbos)} CBO(s) distinto(s) em {len(lotes)} lote(s) "
            f"classificado(s); mapeamento gravado em {caminho_csv!r} "
            f"(prompt em {caminho_prompt!r}); {sem_correspondencia} linha(s) "
            f"da base sem correspondência de CBO."
        ),
        logger=logger,
    )

    return ClassificacaoResult(
        df_enriquecido=df_enriquecido,
        mapeamento=mapeamento,
        sem_correspondencia=sem_correspondencia,
        caminho_csv=caminho_csv,
        caminho_prompt=caminho_prompt,
    )


__all__ = [
    "COLUNA_CBO",
    "COLUNA_MACROFAMILIA",
    "TAMANHO_LOTE",
    "VAR_CREDENCIAL_LLM",
    "MAX_TENTATIVAS",
    "TIMEOUT_SEGUNDOS",
    "ESPERA_BASE_RETRY",
    "CAMINHO_CSV_PADRAO",
    "MACROFAMILIAS",
    "NAO_CLASSIFICADO",
    "ClienteLLM",
    "ClassificacaoResult",
    "extrair_cbos",
    "lotear",
    "montar_prompt",
    "classificar_lote",
    "classificar_cbos",
    "aplicar_mapeamento",
    "descricao_cbo",
    "nivel_cbo",
    "familia_sugerida",
    "lideranca",
    "verificar_credencial_llm",
    "LIMIAR_ALERTA_NAO_CLASSIFICADO",
]
