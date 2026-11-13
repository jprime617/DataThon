"""Classifica as CBOs pela API, com os mesmos prompts usados no chat (TAX-06).

A classificação oficial do painel foi feita **via chat**: cada `prompts/lote_NN.txt`
foi colado na interface do modelo e a resposta salva em `respostas/lote_NN.json`
(ver `COMO_USAR.md`). Este script é o caminho reproduzível pela API: lê **os
mesmos arquivos de prompt**, envia cada lote ao provedor escolhido e grava a
resposta no **mesmo formato** (`{"<cbo>": {"macrofamilia", "nivel",
"justificativa"}}`), pronta para o pipeline ler com `LLM_PROVIDER=arquivo`.

A chave da API vem **só** da variável de ambiente `LLM_API_KEY` e nunca é
gravada. Por padrão as respostas vão para `ia_cbo/respostas_api/`, para não
sobrescrever as respostas oficiais do chat.

Exemplos::

    python ia_cbo/classificar.py --help
    export LLM_API_KEY="..."            # nunca no repositório
    python ia_cbo/classificar.py --provedor anthropic --modelo claude-opus-5-5
    python ia_cbo/classificar.py --lotes 01 02 --saida /tmp/teste_api

Não foi executado para o painel: a execução oficial foi via chat, e os prompts
e as respostas estão versionados em `ia_cbo/`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.erros import ErroDeValidacao  # noqa: E402
from src.cbo_ia import (  # noqa: E402
    MAX_TENTATIVAS,
    MODELO_PADRAO,
    MODELO_PADRAO_GEMINI,
    PASTA_IA_CBO,
    PROVEDOR_ANTHROPIC,
    PROVEDOR_GEMINI,
    TIMEOUT_SEGUNDOS,
    VAR_CREDENCIAL_LLM,
    _extrair_mapeamento,
    verificar_credencial_llm,
)

PASTA_PROMPTS = PASTA_IA_CBO / "prompts"
PASTA_SAIDA_PADRAO = PASTA_IA_CBO / "respostas_api"
META_CHAT = RAIZ / "data_processed" / "cbo_macrofamilias.csv.meta.json"


def modelo_do_chat(meta: Path = META_CHAT) -> str:
    """O modelo da classificação oficial (via chat), para a API repetir o mesmo; senão o padrão do pipeline."""
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("modelo") or MODELO_PADRAO
    except (OSError, ValueError):
        return MODELO_PADRAO


MODELOS_PADRAO = {PROVEDOR_ANTHROPIC: modelo_do_chat(), PROVEDOR_GEMINI: MODELO_PADRAO_GEMINI}


def criar_cliente(provedor: str, modelo: str | None, env=None):
    """Cliente da API (`src.cbo_ia`), com a chave lida de `LLM_API_KEY`; falha antes de qualquer chamada sem ela."""
    from src.cbo_ia import ClienteClaude, ClienteGemini

    chave = verificar_credencial_llm(env)
    classe = {PROVEDOR_ANTHROPIC: ClienteClaude, PROVEDOR_GEMINI: ClienteGemini}[provedor]
    return classe(chave, modelo or MODELOS_PADRAO[provedor])


def codigos_do_prompt(prompt: str) -> set[str]:
    """Os códigos CBO que o lote pede (linhas `- <código> ...` do prompt)."""
    codigos = set()
    for linha in prompt.splitlines():
        partes = linha.strip().lstrip("-•* ").split()
        if partes and partes[0].isdigit() and 5 <= len(partes[0]) <= 6:
            codigos.add(partes[0].zfill(6))
    return codigos


def classificar_lotes(prompts: list[Path], saida: Path, cliente, *, sobrescrever: bool = False,
                      tentativas: int = MAX_TENTATIVAS, timeout: int = TIMEOUT_SEGUNDOS,
                      espera: float = 2.0, log=print) -> dict[str, int]:
    """Envia cada prompt ao `cliente` e grava `saida/<lote>.json`. Devolve {lote: códigos recebidos}.

    Um lote cuja resposta não traz JSON válido é tentado de novo até
    `tentativas` vezes; se continuar vazio, o lote fica de fora e aparece no log.
    """
    saida.mkdir(parents=True, exist_ok=True)
    resultado: dict[str, int] = {}
    for prompt_arquivo in prompts:
        destino = saida / f"{prompt_arquivo.stem}.json"
        if destino.exists() and not sobrescrever:
            log(f"{prompt_arquivo.stem}: já existe em {destino}, pulando (use --sobrescrever)")
            continue
        prompt = prompt_arquivo.read_text(encoding="utf-8")
        esperados = codigos_do_prompt(prompt)
        mapeamento: dict = {}
        for tentativa in range(1, tentativas + 1):
            try:
                mapeamento = _extrair_mapeamento(cliente.classificar(prompt, timeout=timeout))
            except Exception as exc:  # noqa: BLE001 - registra e tenta de novo
                log(f"{prompt_arquivo.stem}: tentativa {tentativa} falhou ({type(exc).__name__}: {exc})")
                mapeamento = {}
            if mapeamento:
                break
            time.sleep(espera * tentativa)
        if not mapeamento:
            log(f"{prompt_arquivo.stem}: sem JSON válido após {tentativas} tentativas; lote fora")
            continue
        destino.write_text(json.dumps(mapeamento, ensure_ascii=False, indent=1), encoding="utf-8")
        faltam = len(esperados - {str(k).zfill(6) for k in mapeamento}) if esperados else 0
        resultado[prompt_arquivo.stem] = len(mapeamento)
        log(f"{prompt_arquivo.stem}: {len(mapeamento)} códigos gravados em {destino}"
            + (f" ({faltam} do prompt ficaram sem resposta)" if faltam else ""))
    return resultado


def _argumentos(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python ia_cbo/classificar.py",
        description="Classifica as CBOs pela API com os mesmos prompts de ia_cbo/prompts/ (usados no chat) e grava "
                    "as respostas no formato que o pipeline lê (LLM_PROVIDER=arquivo).",
        epilog=f"A chave da API vem da variável de ambiente {VAR_CREDENCIAL_LLM} e nunca é gravada. "
               "A execução oficial do painel foi via chat; ver ia_cbo/COMO_USAR.md e docs/COMO_RODAR.md.")
    p.add_argument("--provedor", choices=[PROVEDOR_ANTHROPIC, PROVEDOR_GEMINI], default=PROVEDOR_ANTHROPIC,
                   help="API a chamar (padrão: %(default)s)")
    p.add_argument("--modelo", help=f"modelo (padrão: {MODELOS_PADRAO[PROVEDOR_ANTHROPIC]}, o mesmo do chat, na "
                                    f"Anthropic; {MODELO_PADRAO_GEMINI} no Gemini)")
    p.add_argument("--prompts", type=Path, default=PASTA_PROMPTS, help="pasta com lote_NN.txt (padrão: ia_cbo/prompts)")
    p.add_argument("--saida", type=Path, default=PASTA_SAIDA_PADRAO,
                   help="pasta das respostas lote_NN.json (padrão: ia_cbo/respostas_api, separada das do chat)")
    p.add_argument("--lotes", nargs="*", default=None, help="só estes lotes (ex.: 01 02 23); padrão: todos")
    p.add_argument("--sobrescrever", action="store_true", help="refaz lotes que já têm resposta na saída")
    p.add_argument("--tentativas", type=int, default=MAX_TENTATIVAS, help="tentativas por lote (padrão: %(default)s)")
    p.add_argument("--timeout", type=int, default=TIMEOUT_SEGUNDOS, help="timeout por chamada, em s (padrão: %(default)s)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _argumentos(argv)
    prompts = sorted(args.prompts.glob("lote_*.txt"))
    if args.lotes:
        pedidos = {f"lote_{n.zfill(2)}" for n in args.lotes}
        prompts = [p for p in prompts if p.stem in pedidos]
    if not prompts:
        print(f"Nenhum prompt lote_*.txt em {args.prompts}", file=sys.stderr)
        return 1
    try:
        cliente = criar_cliente(args.provedor, args.modelo, os.environ)
    except ErroDeValidacao as exc:
        print(exc, file=sys.stderr)
        return 1
    resultado = classificar_lotes(prompts, args.saida, cliente, sobrescrever=args.sobrescrever,
                                  tentativas=args.tentativas, timeout=args.timeout)
    print(f"{len(resultado)} de {len(prompts)} lotes gravados em {args.saida}.")
    return 0 if len(resultado) == len(prompts) else 2


if __name__ == "__main__":
    sys.exit(main())
