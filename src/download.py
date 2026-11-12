"""Baixa o Novo CAGED (MOV, FOR, EXC) de 202409 a 202608 do FTP do MTE (M5.C1).

Retomável: cada arquivo vai para `<nome>.part` e continua de onde parou (REST);
um arquivo final com o tamanho do servidor é pulado. Não extrai: o M5.C3 extrai
um arquivo por vez, lê e apaga o texto.

Uso::

    python -m src.download        # grava em data/raw/caged/ (fora do Git)
"""

from __future__ import annotations

import ftplib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "raw" / "caged"
HOST = "ftp.mtps.gov.br"
BASE = "/pdet/microdados/NOVO CAGED"
TIPOS = ("MOV", "FOR", "EXC")
INICIO, FIM = 202409, 202608  # janela D1: set/24–ago/26


def competencias(inicio: int = INICIO, fim: int = FIM) -> list[int]:
    """Lista AAAAMM de `inicio` a `fim`, inclusive."""
    saida, ano, mes = [], inicio // 100, inicio % 100
    while ano * 100 + mes <= fim:
        saida.append(ano * 100 + mes)
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return saida


def arquivos_remotos(inicio: int = INICIO, fim: int = FIM) -> list[str]:
    return [
        f"{BASE}/{c // 100}/{c}/CAGED{t}{c}.7z"
        for c in competencias(inicio, fim)
        for t in TIPOS
    ]


def baixar(ftp: ftplib.FTP, remoto: str, local: Path) -> None:
    tamanho = ftp.size(remoto)
    if local.exists() and local.stat().st_size == tamanho:
        return
    parcial = local.with_name(local.name + ".part")
    inicio = parcial.stat().st_size if parcial.exists() else 0
    if inicio > tamanho:
        parcial.unlink()
        inicio = 0
    if inicio < tamanho:
        with parcial.open("ab") as saida:
            try:
                ftp.retrbinary(f"RETR {remoto}", saida.write, blocksize=1 << 20, rest=inicio or None)
            except ftplib.all_errors as exc:
                # O canal de controle pode cair depois de todos os bytes chegarem;
                # quem decide é a conferência de tamanho abaixo.
                print(f"[!!] {local.name}: {exc!r}", flush=True)
    if parcial.stat().st_size != tamanho:
        raise RuntimeError(f"{local.name}: incompleto; rode de novo para retomar.")
    parcial.replace(local)


def main() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    remotos = arquivos_remotos()
    for i, remoto in enumerate(remotos, 1):
        local = DESTINO / remoto.rsplit("/", 1)[1]
        # Uma conexão por arquivo: as transferências longas derrubam o controle.
        ftp = ftplib.FTP(HOST, timeout=120, encoding="latin-1")
        ftp.login()
        try:
            baixar(ftp, remoto, local)
        finally:
            try:
                ftp.quit()
            except ftplib.all_errors:
                ftp.close()
        print(f"[{i}/{len(remotos)}] {local.name} ({local.stat().st_size:,} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
