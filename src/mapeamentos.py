"""Tabelas de domínio do dicionário de dados (R2.5).

Este módulo carrega os domínios categóricos a partir do
`Dados/Dicionario_de_dados.xlsx` (via `openpyxl`) e os expõe como dicionários
`código → rótulo`, consumidos pelo Limpador (`limpeza.decodificar_dominios`)
para substituir códigos por rótulos legíveis.

As abas do dicionário seguem todas o mesmo layout: a primeira linha é o
cabeçalho `('Código', 'Descrição')` e as linhas seguintes trazem o par
código/rótulo. A maioria dos domínios usa código inteiro; a seção CNAE
(`seção`) usa código textual (A–Z).

Também expõe a constante `MACROFAMILIAS` — o conjunto fechado de macrofamílias
de CBO (entre 5 e 12, incluindo `Não classificado`) usado por `cbo_ia.py` — e
`MESORREGIAO_POR_MUNICIPIO`, que dá a mesorregião do IBGE de cada município.

Carregamento tardio dos domínios
--------------------------------
Os domínios são lidos do `.xlsx` na **primeira vez** que uma das constantes é
acessada, não na importação do módulo (PEP 562). Isso importa porque a cadeia
`dashboard/app.py → src.agregador → src.cbo_ia → src.mapeamentos` chega até aqui:
com leitura na importação, publicar o dashboard no App Service exigiria embarcar
a pasta `Dados/` e o `openpyxl` só para abrir a tela. O dashboard consome apenas
as tabelas agregadas (R7.7) e, com o carregamento tardio, nunca toca no
dicionário.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from src.erros import ErroDeValidacao

# Caminho padrão do dicionário de dados (relativo à raiz do projeto).
_RAIZ_PROJETO = Path(__file__).resolve().parent.parent
CAMINHO_DICIONARIO = _RAIZ_PROJETO / "Dados" / "Dicionario_de_dados.xlsx"

# Rótulo de fallback para CBOs sem macrofamília atribuída pelo LLM (R5.6).
NAO_CLASSIFICADO = "Não classificado"

# Conjunto fechado de macrofamílias de CBO (R5.2): entre 5 e 12 famílias,
# incluindo obrigatoriamente `Não classificado` como categoria de fallback.
# A macrofamília é o OFÍCIO da ocupação, nunca o setor do empregador: faxineira
# em fábrica têxtil é "Serviços de apoio"; costureira é "Têxtil" em qualquer setor.
FAMILIA_OPERACAO = "Operação de linha e processo"
FAMILIA_METALMECANICA = "Metalmecânica e eletroeletrônica"
FAMILIA_CONSTRUCAO = "Construção civil e extração"
FAMILIA_TEXTIL = "Têxtil, confecção, couro e calçados"
FAMILIA_ALIMENTOS = "Alimentos e bebidas"
FAMILIA_MADEIRA = "Madeira, móveis, cerâmica e vidro"
FAMILIA_MANUTENCAO = "Manutenção e reparação"
FAMILIA_LOGISTICA = "Logística e transporte"
FAMILIA_ENGENHARIA = "Engenharia, técnicos industriais e TI"
FAMILIA_ADMINISTRATIVO = "Administrativo e comercial"
FAMILIA_APOIO = "Serviços de apoio e outros"

MACROFAMILIAS: list[str] = [
    FAMILIA_OPERACAO,
    FAMILIA_METALMECANICA,
    FAMILIA_CONSTRUCAO,
    FAMILIA_TEXTIL,
    FAMILIA_ALIMENTOS,
    FAMILIA_MADEIRA,
    FAMILIA_MANUTENCAO,
    FAMILIA_LOGISTICA,
    FAMILIA_ENGENHARIA,
    FAMILIA_ADMINISTRATIVO,
    FAMILIA_APOIO,
    NAO_CLASSIFICADO,
]

# Regra de desempate: família sugerida pelo prefixo da CBO. O prefixo mais longo
# vence (784 → Operação, mesmo com 78 ausente; 414 → Logística dentro do grande
# grupo 4). Prefixos fora da tabela — inclusive o grande grupo 1 (dirigentes,
# que vão para a família da área dirigida) — não têm sugestão: a IA decide pela
# descrição.
FAMILIA_POR_PREFIXO_CBO: dict[str, str] = {
    **dict.fromkeys(["781", "784", "74", "81", "82", "83", "86"], FAMILIA_OPERACAO),
    **dict.fromkeys(["72", "73"], FAMILIA_METALMECANICA),
    "71": FAMILIA_CONSTRUCAO,
    "76": FAMILIA_TEXTIL,
    "84": FAMILIA_ALIMENTOS,
    **dict.fromkeys(["75", "77"], FAMILIA_MADEIRA),
    **dict.fromkeys(["91", "95", "99"], FAMILIA_MANUTENCAO),
    **dict.fromkeys(["782", "783", "414", "342"], FAMILIA_LOGISTICA),
    # Grande grupo 2 de exatas/engenharia/TI (20 pesquisadores, 21 exatas e
    # engenharia) e os técnicos industriais do grande grupo 3.
    **dict.fromkeys(["20", "21", "30", "31", "39", "317"], FAMILIA_ENGENHARIA),
    **dict.fromkeys(["4", "25", "35", "52"], FAMILIA_ADMINISTRATIVO),
    # Saúde (22, 322), educação (23, 33), agro (6) e grande grupo 0.
    **dict.fromkeys(["51", "22", "23", "322", "33", "6", "0"], FAMILIA_APOIO),
}

# Nível de qualificação: só 4 valores ordinais, do menor para o maior.
NIVEIS_QUALIFICACAO: list[str] = ["Básico", "Qualificado", "Técnico", "Superior"]

# Nível derivado do 1º dígito da CBO (grande grupo); a IA confirma ou ajusta.
NIVEL_POR_GRANDE_GRUPO: dict[str, str] = {
    "1": "Superior",
    "2": "Superior",
    "3": "Técnico",
    **dict.fromkeys("4567890", "Qualificado"),
}

# Início de descrição que marca liderança (além do grande grupo 1).
PREFIXOS_LIDERANCA = ("Supervisor", "Mestre", "Encarregado", "Chefe", "Gerente", "Diretor")

# Mesorregião do IBGE por Chave_Municipal de 6 dígitos (R6.1).
#
# A pergunta de negócio é sobre *regiões* de Santa Catarina, mas nenhuma das
# bases de origem traz um recorte regional intraestadual: a coluna `região` do
# CAGED é a Grande Região do IBGE e vale 4 (Sul) em todo o estado. As seis
# mesorregiões abaixo são o menor agrupamento regional oficial que responde à
# pergunta — Grande Florianópolis, Norte Catarinense, Oeste Catarinense,
# Serrana, Sul Catarinense e Vale do Itajaí.
#
# Tabela de referência estável do IBGE (localidades/estados/42/municipios),
# embarcada aqui em vez de baixada no pipeline: são 295 pares que não mudam
# entre execuções, e embarcá-los evita uma dependência de rede na agregação.
MESORREGIAO_POR_MUNICIPIO: dict[str, str] = {
    "420005": "Serrana",
    "420010": "Oeste Catarinense",
    "420020": "Vale do Itajaí",
    "420030": "Vale do Itajaí",
    "420040": "Oeste Catarinense",
    "420050": "Oeste Catarinense",
    "420055": "Oeste Catarinense",
    "420060": "Grande Florianópolis",
    "420070": "Grande Florianópolis",
    "420075": "Oeste Catarinense",
    "420080": "Oeste Catarinense",
    "420090": "Grande Florianópolis",
    "420100": "Serrana",
    "420110": "Grande Florianópolis",
    "420120": "Grande Florianópolis",
    "420125": "Vale do Itajaí",
    "420127": "Oeste Catarinense",
    "420130": "Norte Catarinense",
    "420140": "Sul Catarinense",
    "420150": "Sul Catarinense",
    "420160": "Oeste Catarinense",
    "420165": "Oeste Catarinense",
    "420170": "Vale do Itajaí",
    "420180": "Vale do Itajaí",
    "420190": "Vale do Itajaí",
    "420195": "Sul Catarinense",
    "420200": "Vale do Itajaí",
    "420205": "Norte Catarinense",
    "420207": "Sul Catarinense",
    "420208": "Oeste Catarinense",
    "420209": "Oeste Catarinense",
    "420210": "Vale do Itajaí",
    "420213": "Norte Catarinense",
    "420215": "Oeste Catarinense",
    "420220": "Vale do Itajaí",
    "420230": "Grande Florianópolis",
    "420240": "Vale do Itajaí",
    "420243": "Serrana",
    "420245": "Vale do Itajaí",
    "420250": "Serrana",
    "420253": "Oeste Catarinense",
    "420257": "Oeste Catarinense",
    "420260": "Serrana",
    "420270": "Vale do Itajaí",
    "420280": "Sul Catarinense",
    "420285": "Vale do Itajaí",
    "420287": "Serrana",
    "420290": "Vale do Itajaí",
    "420300": "Oeste Catarinense",
    "420310": "Oeste Catarinense",
    "420315": "Oeste Catarinense",
    "420320": "Vale do Itajaí",
    "420325": "Serrana",
    "420330": "Norte Catarinense",
    "420340": "Serrana",
    "420350": "Oeste Catarinense",
    "420360": "Serrana",
    "420370": "Grande Florianópolis",
    "420380": "Norte Catarinense",
    "420390": "Oeste Catarinense",
    "420395": "Sul Catarinense",
    "420400": "Oeste Catarinense",
    "420410": "Oeste Catarinense",
    "420415": "Serrana",
    "420417": "Serrana",
    "420419": "Vale do Itajaí",
    "420420": "Oeste Catarinense",
    "420425": "Sul Catarinense",
    "420430": "Oeste Catarinense",
    "420435": "Oeste Catarinense",
    "420440": "Oeste Catarinense",
    "420445": "Oeste Catarinense",
    "420450": "Norte Catarinense",
    "420455": "Serrana",
    "420460": "Sul Catarinense",
    "420470": "Oeste Catarinense",
    "420475": "Oeste Catarinense",
    "420480": "Serrana",
    "420490": "Oeste Catarinense",
    "420500": "Oeste Catarinense",
    "420510": "Vale do Itajaí",
    "420515": "Vale do Itajaí",
    "420517": "Oeste Catarinense",
    "420519": "Sul Catarinense",
    "420520": "Oeste Catarinense",
    "420530": "Oeste Catarinense",
    "420535": "Oeste Catarinense",
    "420540": "Grande Florianópolis",
    "420543": "Oeste Catarinense",
    "420545": "Sul Catarinense",
    "420550": "Oeste Catarinense",
    "420555": "Serrana",
    "420560": "Oeste Catarinense",
    "420570": "Sul Catarinense",
    "420580": "Norte Catarinense",
    "420590": "Vale do Itajaí",
    "420600": "Grande Florianópolis",
    "420610": "Sul Catarinense",
    "420620": "Sul Catarinense",
    "420630": "Vale do Itajaí",
    "420640": "Oeste Catarinense",
    "420650": "Norte Catarinense",
    "420660": "Oeste Catarinense",
    "420665": "Oeste Catarinense",
    "420670": "Oeste Catarinense",
    "420675": "Oeste Catarinense",
    "420680": "Oeste Catarinense",
    "420690": "Vale do Itajaí",
    "420700": "Sul Catarinense",
    "420710": "Vale do Itajaí",
    "420720": "Sul Catarinense",
    "420730": "Sul Catarinense",
    "420740": "Vale do Itajaí",
    "420750": "Vale do Itajaí",
    "420757": "Oeste Catarinense",
    "420760": "Oeste Catarinense",
    "420765": "Oeste Catarinense",
    "420768": "Oeste Catarinense",
    "420770": "Oeste Catarinense",
    "420775": "Oeste Catarinense",
    "420780": "Oeste Catarinense",
    "420785": "Oeste Catarinense",
    "420790": "Norte Catarinense",
    "420800": "Oeste Catarinense",
    "420810": "Norte Catarinense",
    "420820": "Vale do Itajaí",
    "420830": "Vale do Itajaí",
    "420840": "Oeste Catarinense",
    "420845": "Norte Catarinense",
    "420850": "Vale do Itajaí",
    "420860": "Oeste Catarinense",
    "420870": "Sul Catarinense",
    "420880": "Sul Catarinense",
    "420890": "Norte Catarinense",
    "420895": "Oeste Catarinense",
    "420900": "Oeste Catarinense",
    "420910": "Norte Catarinense",
    "420915": "Vale do Itajaí",
    "420917": "Oeste Catarinense",
    "420920": "Oeste Catarinense",
    "420930": "Serrana",
    "420940": "Sul Catarinense",
    "420945": "Oeste Catarinense",
    "420950": "Vale do Itajaí",
    "420960": "Sul Catarinense",
    "420970": "Oeste Catarinense",
    "420980": "Grande Florianópolis",
    "420985": "Oeste Catarinense",
    "420990": "Vale do Itajaí",
    "421000": "Vale do Itajaí",
    "421003": "Oeste Catarinense",
    "421005": "Oeste Catarinense",
    "421010": "Norte Catarinense",
    "421020": "Grande Florianópolis",
    "421030": "Norte Catarinense",
    "421040": "Sul Catarinense",
    "421050": "Oeste Catarinense",
    "421055": "Oeste Catarinense",
    "421060": "Norte Catarinense",
    "421070": "Oeste Catarinense",
    "421080": "Sul Catarinense",
    "421085": "Vale do Itajaí",
    "421090": "Oeste Catarinense",
    "421100": "Oeste Catarinense",
    "421105": "Serrana",
    "421110": "Norte Catarinense",
    "421120": "Sul Catarinense",
    "421125": "Sul Catarinense",
    "421130": "Vale do Itajaí",
    "421140": "Oeste Catarinense",
    "421145": "Oeste Catarinense",
    "421150": "Grande Florianópolis",
    "421160": "Sul Catarinense",
    "421165": "Oeste Catarinense",
    "421170": "Sul Catarinense",
    "421175": "Serrana",
    "421180": "Oeste Catarinense",
    "421185": "Oeste Catarinense",
    "421187": "Oeste Catarinense",
    "421189": "Serrana",
    "421190": "Grande Florianópolis",
    "421200": "Oeste Catarinense",
    "421205": "Serrana",
    "421210": "Oeste Catarinense",
    "421220": "Norte Catarinense",
    "421223": "Oeste Catarinense",
    "421225": "Sul Catarinense",
    "421227": "Oeste Catarinense",
    "421230": "Grande Florianópolis",
    "421240": "Sul Catarinense",
    "421250": "Vale do Itajaí",
    "421260": "Oeste Catarinense",
    "421265": "Sul Catarinense",
    "421270": "Vale do Itajaí",
    "421280": "Vale do Itajaí",
    "421290": "Oeste Catarinense",
    "421300": "Oeste Catarinense",
    "421310": "Oeste Catarinense",
    "421315": "Oeste Catarinense",
    "421320": "Vale do Itajaí",
    "421330": "Serrana",
    "421335": "Serrana",
    "421340": "Oeste Catarinense",
    "421350": "Vale do Itajaí",
    "421360": "Norte Catarinense",
    "421370": "Vale do Itajaí",
    "421380": "Sul Catarinense",
    "421390": "Oeste Catarinense",
    "421400": "Vale do Itajaí",
    "421410": "Vale do Itajaí",
    "421415": "Oeste Catarinense",
    "421420": "Oeste Catarinense",
    "421430": "Grande Florianópolis",
    "421440": "Oeste Catarinense",
    "421450": "Vale do Itajaí",
    "421460": "Vale do Itajaí",
    "421470": "Vale do Itajaí",
    "421480": "Vale do Itajaí",
    "421490": "Sul Catarinense",
    "421500": "Norte Catarinense",
    "421505": "Serrana",
    "421507": "Oeste Catarinense",
    "421510": "Vale do Itajaí",
    "421520": "Oeste Catarinense",
    "421530": "Vale do Itajaí",
    "421535": "Oeste Catarinense",
    "421540": "Oeste Catarinense",
    "421545": "Sul Catarinense",
    "421550": "Serrana",
    "421555": "Oeste Catarinense",
    "421560": "Sul Catarinense",
    "421565": "Sul Catarinense",
    "421567": "Norte Catarinense",
    "421568": "Oeste Catarinense",
    "421569": "Oeste Catarinense",
    "421570": "Grande Florianópolis",
    "421575": "Oeste Catarinense",
    "421580": "Norte Catarinense",
    "421590": "Grande Florianópolis",
    "421600": "Oeste Catarinense",
    "421605": "Serrana",
    "421610": "Oeste Catarinense",
    "421620": "Norte Catarinense",
    "421625": "Oeste Catarinense",
    "421630": "Grande Florianópolis",
    "421635": "Vale do Itajaí",
    "421640": "Sul Catarinense",
    "421650": "Serrana",
    "421660": "Grande Florianópolis",
    "421670": "Oeste Catarinense",
    "421680": "Serrana",
    "421690": "Oeste Catarinense",
    "421700": "Sul Catarinense",
    "421710": "Sul Catarinense",
    "421715": "Oeste Catarinense",
    "421720": "Oeste Catarinense",
    "421725": "Grande Florianópolis",
    "421730": "Oeste Catarinense",
    "421740": "Norte Catarinense",
    "421750": "Oeste Catarinense",
    "421755": "Oeste Catarinense",
    "421760": "Sul Catarinense",
    "421770": "Sul Catarinense",
    "421775": "Oeste Catarinense",
    "421780": "Vale do Itajaí",
    "421790": "Oeste Catarinense",
    "421795": "Oeste Catarinense",
    "421800": "Grande Florianópolis",
    "421810": "Sul Catarinense",
    "421820": "Vale do Itajaí",
    "421825": "Norte Catarinense",
    "421830": "Norte Catarinense",
    "421835": "Sul Catarinense",
    "421840": "Sul Catarinense",
    "421850": "Oeste Catarinense",
    "421860": "Vale do Itajaí",
    "421870": "Sul Catarinense",
    "421875": "Oeste Catarinense",
    "421880": "Sul Catarinense",
    "421885": "Oeste Catarinense",
    "421890": "Serrana",
    "421895": "Serrana",
    "421900": "Sul Catarinense",
    "421910": "Oeste Catarinense",
    "421915": "Serrana",
    "421917": "Oeste Catarinense",
    "421920": "Vale do Itajaí",
    "421930": "Oeste Catarinense",
    "421935": "Vale do Itajaí",
    "421940": "Vale do Itajaí",
    "421950": "Oeste Catarinense",
    "421960": "Oeste Catarinense",
    "421970": "Oeste Catarinense",
    "421985": "Serrana",
    "422000": "Sul Catarinense",
}

# Rótulo aplicado a municípios fora da tabela (nenhum, hoje: ela cobre os 295).
REGIAO_DESCONHECIDA = "Não identificada"

# Mapeamento: nome da constante de domínio → nome da aba no dicionário.
_ABAS_DOMINIO: dict[str, str] = {
    "GRAU_INSTRUCAO": "graudeinstrução",
    "RACA_COR": "raçacor",
    "SEXO": "sexo",
    "TIPO_MOVIMENTACAO": "tipomovimentação",
    "CATEGORIA": "categoria",
    "TAM_ESTAB_JAN": "tamestabjan",
    "UNIDADE_SALARIO": "unidadesaláriocódigo",
    "SECAO_CNAE": "seção",
    # Descrição de cada ocupação (código inteiro), usada no prompt da IA (R5).
    "CBO_OCUPACAO": "cbo2002ocupação",
}


def _normalizar_codigo(valor: object) -> object:
    """Normaliza o código lido da planilha.

    Códigos numéricos vêm como `int`/`float` do openpyxl; convertemos floats
    inteiros (ex.: `1.0`) para `int`. Códigos textuais (seção CNAE) são mantidos
    como string sem espaços ao redor.
    """
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str):
        return valor.strip()
    return valor


def _carregar_aba(
    wb: "openpyxl.workbook.workbook.Workbook", aba: str
) -> dict[object, str]:
    """Lê uma aba de domínio e retorna o dicionário `código → rótulo`.

    Pula a linha de cabeçalho e ignora linhas sem código ou sem rótulo.
    """
    if aba not in wb.sheetnames:
        raise ErroDeValidacao(
            f"Aba de domínio ausente no dicionário: {aba!r}. "
            f"Abas disponíveis: {wb.sheetnames}"
        )

    ws = wb[aba]
    mapa: dict[object, str] = {}
    for indice, (codigo, rotulo) in enumerate(ws.iter_rows(values_only=True)):
        if indice == 0:
            # Primeira linha é o cabeçalho ('Código', 'Descrição').
            continue
        if codigo is None or rotulo is None:
            continue
        chave = _normalizar_codigo(codigo)
        mapa[chave] = str(rotulo).strip()

    if not mapa:
        raise ErroDeValidacao(
            f"Aba de domínio {aba!r} não produziu nenhum par código→rótulo."
        )
    return mapa


def carregar_dominios(
    caminho: str | Path = CAMINHO_DICIONARIO,
) -> dict[str, dict[object, str]]:
    """Carrega todos os domínios categóricos do dicionário de dados (R2.5).

    Args:
        caminho: caminho do `Dicionario_de_dados.xlsx`. Usa o padrão do projeto
            quando omitido.

    Returns:
        Dicionário cujas chaves são os nomes das constantes de domínio
        (`GRAU_INSTRUCAO`, `RACA_COR`, ...) e cujos valores são os mapas
        `código → rótulo` correspondentes.

    Raises:
        ErroDeValidacao: se o arquivo estiver ausente/ilegível ou se alguma aba
            esperada estiver ausente/vazia.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ErroDeValidacao(
            f"Dicionário de dados ausente ou inacessível: {caminho}"
        )

    try:
        wb = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001 - reempacota como erro de validação
        raise ErroDeValidacao(
            f"Falha ao ler o dicionário de dados {caminho}: {exc}"
        ) from exc

    try:
        return {
            nome: _carregar_aba(wb, aba) for nome, aba in _ABAS_DOMINIO.items()
        }
    finally:
        wb.close()


# Cache dos domínios carregados; preenchido na primeira consulta (ver `__getattr__`).
_DOMINIOS: dict[str, dict[object, str]] | None = None


def __getattr__(nome: str) -> dict[object, str]:
    """Resolve as constantes de domínio sob demanda (PEP 562).

    `GRAU_INSTRUCAO`, `RACA_COR`, `SEXO`, `TIPO_MOVIMENTACAO`, `CATEGORIA`,
    `TAM_ESTAB_JAN`, `UNIDADE_SALARIO` e `SECAO_CNAE` continuam importáveis como
    constantes (`from src.mapeamentos import SECAO_CNAE`), mas o dicionário só é
    lido do disco na primeira vez que uma delas é acessada — e uma única vez,
    graças ao cache em `_DOMINIOS`. Quem importa o módulo sem tocar nos domínios
    (o dashboard, via `src.agregador`) nunca abre o `.xlsx`.

    Raises:
        AttributeError: para qualquer nome que não seja um domínio conhecido.
        ErroDeValidacao: se o dicionário estiver ausente/ilegível no primeiro
            acesso (propagada de `carregar_dominios`).
    """
    global _DOMINIOS
    if nome not in _ABAS_DOMINIO:
        raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")
    if _DOMINIOS is None:
        _DOMINIOS = carregar_dominios()
    return _DOMINIOS[nome]


__all__ = [
    "MACROFAMILIAS",
    "NAO_CLASSIFICADO",
    "MESORREGIAO_POR_MUNICIPIO",
    "REGIAO_DESCONHECIDA",
    "CAMINHO_DICIONARIO",
    "carregar_dominios",
    "GRAU_INSTRUCAO",
    "RACA_COR",
    "SEXO",
    "TIPO_MOVIMENTACAO",
    "CATEGORIA",
    "TAM_ESTAB_JAN",
    "UNIDADE_SALARIO",
    "SECAO_CNAE",
    "CBO_OCUPACAO",
    "FAMILIA_POR_PREFIXO_CBO",
    "NIVEIS_QUALIFICACAO",
    "NIVEL_POR_GRANDE_GRUPO",
    "PREFIXOS_LIDERANCA",
]
