"""Baixa e extrai a RAIS 2025 (vínculos, região Sul) do FTP do MTE (M4.C1).

O M4 usa só a RAIS 2025: o estoque de 31/12/2025 cai dentro da janela
set/25–ago/26 do CAGED e serve de aproximação do estoque médio (PLANO_RETA_FINAL,
M4). Este script traz o arquivo de vínculos do Sul (que contém SC) e o layout
oficial dos vínculos, para conferir colunas e códigos no layout e não de memória.

Retomável: o download vai para `<arquivo>.part` e continua de onde parou (REST do
FTP); um arquivo final com o tamanho do servidor é pulado; a extração é pulada se
o `.txt` extraído já existe.

Extração: usa o `7z` de linha de comando se existir; senão o `bsdtar`
(libarchive com liblzma, que lê `.7z`). Nenhuma dependência Python nova.

Uso::

    python scripts/baixar_rais.py            # baixa layout + vínculos Sul e extrai
    python scripts/baixar_rais.py --sem-extrair

Grava em `data/raw/rais/2025/` (ignorado pelo Git — dados grandes nunca vão
para o repositório).
"""

from __future__ import annotations

import argparse
import ftplib
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "raw" / "rais" / "2025"

HOST = "ftp.mtps.gov.br"
# O servidor lista nomes em Latin-1 (a pasta "vínculos" vem com \xed).
ENCODING_FTP = "latin-1"

# (caminho remoto, nome local)
ARQUIVOS = [
    ("/pdet/microdados/RAIS/Layouts/vínculos/RAIS_vinculos_layout.xls", "RAIS_vinculos_layout.xls"),
    ("/pdet/microdados/RAIS/2025/RAIS_VINC_PUB_SUL.7z", "RAIS_VINC_PUB_SUL.7z"),
]

BLOCO = 1 << 20  # 1 MiB


def precisa_baixar(local: Path, tamanho_remoto: int | None) -> bool:
    """O arquivo final só é aceito se existe e tem o tamanho do servidor.

    Sem tamanho remoto (servidor não informou), basta existir.
    """
    if not local.exists():
        return True
    if tamanho_remoto is None:
        return False
    return local.stat().st_size != tamanho_remoto


def comando_extracao(arquivo: Path, destino: Path) -> list[str]:
    """Monta o comando de extração: `7z` se houver, senão `bsdtar`."""
    if shutil.which("7z"):
        return ["7z", "x", "-y", f"-o{destino}", str(arquivo)]
    if shutil.which("bsdtar"):
        return ["bsdtar", "-xf", str(arquivo), "-C", str(destino)]
    raise RuntimeError("Nem `7z` nem `bsdtar` encontrados para extrair o .7z.")


def baixar(ftp: ftplib.FTP, remoto: str, local: Path) -> None:
    try:
        tamanho = ftp.size(remoto)
    except ftplib.error_perm:
        tamanho = None
    if not precisa_baixar(local, tamanho):
        print(f"[ok] {local.name} já baixado ({local.stat().st_size:,} bytes)")
        return

    parcial = local.with_name(local.name + ".part")
    inicio = parcial.stat().st_size if parcial.exists() else 0
    if tamanho is not None and inicio > tamanho:
        parcial.unlink()
        inicio = 0
    print(f"[..] {local.name}: {inicio:,} de {tamanho or '?':,} bytes" if tamanho else f"[..] {local.name}")

    feito = inicio
    proximo_aviso = inicio + 50 * BLOCO

    if tamanho is not None and inicio == tamanho:
        parcial.replace(local)
        print(f"[ok] {local.name} ({tamanho:,} bytes, completado numa execução anterior)")
        return

    with parcial.open("ab") as saida:

        def gravar(dados: bytes) -> None:
            nonlocal feito, proximo_aviso
            saida.write(dados)
            feito += len(dados)
            if feito >= proximo_aviso:
                pct = f" ({feito / tamanho:.0%})" if tamanho else ""
                print(f"     {feito / BLOCO:,.0f} MiB{pct}", flush=True)
                proximo_aviso += 50 * BLOCO

        try:
            ftp.retrbinary(f"RETR {remoto}", gravar, blocksize=BLOCO, rest=inicio or None)
        except ftplib.all_errors as exc:
            # Em transferências longas o canal de controle fica ocioso e cai antes
            # do "226 Transfer complete", mesmo com todos os bytes recebidos. Quem
            # decide é a conferência de tamanho logo abaixo.
            print(f"[!!] conexão de controle: {exc!r}", flush=True)

    if tamanho is not None and parcial.stat().st_size != tamanho:
        raise RuntimeError(
            f"{local.name}: baixou {parcial.stat().st_size:,} de {tamanho:,} bytes; rode de novo para retomar."
        )
    parcial.replace(local)
    print(f"[ok] {local.name} ({local.stat().st_size:,} bytes)")


def extrair(arquivo: Path) -> None:
    destino = arquivo.parent
    # A RAIS 2025 extrai como `RAIS_VINC_PUB_SUL.COMT` (não `.txt`): vale
    # qualquer irmão com o mesmo radical que não seja o próprio .7z nem um .part.
    ja_extraidos = [
        p for p in destino.glob(arquivo.stem + ".*")
        if p != arquivo and p.suffix.lower() not in {".7z", ".part"}
    ]
    if ja_extraidos:
        print(f"[ok] já extraído: {', '.join(p.name for p in ja_extraidos)}")
        return
    cmd = comando_extracao(arquivo, destino)
    print(f"[..] extraindo com {cmd[0]}")
    subprocess.run(cmd, check=True)
    print("[ok] extraído")


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--sem-extrair", action="store_true", help="só baixa")
    opcoes = args.parse_args(argv)

    DESTINO.mkdir(parents=True, exist_ok=True)
    ftp = ftplib.FTP(HOST, timeout=120, encoding=ENCODING_FTP)
    ftp.login()
    try:
        for remoto, nome in ARQUIVOS:
            baixar(ftp, remoto, DESTINO / nome)
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()

    if not opcoes.sem_extrair:
        for _, nome in ARQUIVOS:
            if nome.endswith(".7z"):
                extrair(DESTINO / nome)
    return 0


if __name__ == "__main__":
    sys.exit(main())
