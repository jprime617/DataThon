from src.download import arquivos_remotos, competencias


def test_janela_tem_24_meses_e_72_arquivos():
    c = competencias()
    assert len(c) == 24 and c[0] == 202409 and c[-1] == 202608
    assert 202412 in c and 202501 in c
    r = arquivos_remotos()
    assert len(r) == 72
    assert r[0] == "/pdet/microdados/NOVO CAGED/2024/202409/CAGEDMOV202409.7z"
    assert r[-1].endswith("/2026/202608/CAGEDEXC202608.7z")
