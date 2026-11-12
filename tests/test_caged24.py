import shutil
import subprocess

import pytest

from src.caged24 import consolidar

pytestmark = pytest.mark.skipif(not (shutil.which("7z") or shutil.which("bsdtar")), reason="sem 7z/bsdtar")

CAB = "competênciamov;uf;município;saldomovimentação;salário"


def _7z(tmp_path, nome, linhas, extra=""):
    txt = tmp_path / f"{nome}.txt"
    txt.write_text(CAB + extra + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    if shutil.which("7z"):
        subprocess.run(["7z", "a", "-y", str(tmp_path / f"{nome}.7z"), str(txt)], check=True, capture_output=True)
    else:
        subprocess.run(["bsdtar", "-acf", str(tmp_path / f"{nome}.7z"), "-C", str(tmp_path), txt.name], check=True)
    txt.unlink()


def test_mov_for_exc_com_peso_e_filtros(tmp_path):
    _7z(tmp_path, "CAGEDMOV202608", ["202608;42;420910;1;2000,00", "202608;35;355030;1;1", "202608;42;420910;-1;1"])
    _7z(tmp_path, "CAGEDFOR202608", ["202608;42;420540;1;1", "202407;42;420540;1;1"])  # fora da janela sai
    _7z(tmp_path, "CAGEDEXC202608", ["202608;42;420540;1;1;202608;1"], extra=";competênciaexc;indicadordeexclusão")
    df = consolidar(tmp_path, destino=tmp_path / "out.parquet", inicio=202608, fim=202608)
    assert sorted(df.tipo_arquivo) == ["EXC", "FOR", "MOV", "MOV"]
    assert "competênciaexc" not in df.columns and set(df.uf) == {"42"}
    adm = df.peso[df["saldomovimentação"] == "1"].sum()
    assert adm == 1  # MOV +1, FOR +1, EXC −1
    assert df.peso[df["saldomovimentação"] == "-1"].sum() == 1
    assert "2000,00" in set(df["salário"])  # texto cru; a limpeza converte
    assert (tmp_path / "out.parquet").exists()
