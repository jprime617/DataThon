"""M4.C2: `ler_rais_sc` filtra SC + CLT num CSV sintético no formato da RAIS 2025."""

from __future__ import annotations

import pandas as pd
import pytest

from src.erros import ErroDeValidacao
from src.rais import COLUNAS_ORIGEM, ler_rais_sc

_CABECALHO = list(COLUNAS_ORIGEM) + ["Raça Cor - Código"]


def _linha(municipio, tipo, ativo, motivo, tempo, subclasse=' 2512800'):
    # Mesma ordem de _CABECALHO; subclasse entre aspas com espaço, como na origem.
    return [municipio, tipo, ativo, motivo, "3", "0" if motivo == "0" else "5",
            tempo, "7", "784205", subclasse, "3210.55", "2"]


def _escrever(tmp_path, linhas):
    caminho = tmp_path / "RAIS_TESTE.COMT"
    texto = ",".join(f'"{c}"' for c in _CABECALHO) + "\n"
    for linha in linhas:
        texto += ",".join(f'"{v}"' if v.startswith(" ") else v for v in linha) + "\n"
    caminho.write_bytes(texto.encode("latin-1"))
    return caminho


@pytest.fixture
def rais(tmp_path):
    return _escrever(tmp_path, [
        _linha("420540", "10", "1", "0", "70.3"),   # SC, CLT indeterminado, ativo
        _linha("420540", "30", "1", "0", "120.0"),  # SC, estatutário → fora
        _linha("431490", "10", "1", "0", "12.0"),   # RS → fora
        _linha("421660", "60", "0", "11", "5.2"),   # SC, CLT determinado, desligado
        _linha("420910", "55", "0", "21", "8.0"),   # SC, aprendiz → fora
    ])


def test_filtra_sc_e_clt(rais, tmp_path):
    destino = tmp_path / "saida.parquet"
    df = ler_rais_sc(rais, destino, chunksize=2)  # força mais de um bloco
    assert list(df["chave_municipal"]) == ["420540", "421660"]
    assert list(df["tipo_vinculo"]) == [10, 60]
    assert destino.exists()
    pd.testing.assert_frame_equal(pd.read_parquet(destino), df)


def test_tipos_e_limpeza(rais):
    df = ler_rais_sc(rais, None)
    assert list(df["ativo_31dez"]) == [1, 0]
    assert list(df["motivo_desligamento"]) == [0, 11]
    assert df["tempo_emprego_meses"].tolist() == pytest.approx([70.3, 5.2], rel=1e-5)
    assert set(df["subclasse"]) == {"2512800"}
    assert "Raça Cor - Código" not in df.columns


def test_arquivo_ausente(tmp_path):
    with pytest.raises(ErroDeValidacao, match="ausente"):
        ler_rais_sc(tmp_path / "nao_existe.COMT", None)


def test_coluna_faltando(tmp_path):
    caminho = tmp_path / "ruim.COMT"
    caminho.write_bytes('"Município - Código","Tipo Vínculo - Código"\n420540,10\n'.encode("latin-1"))
    with pytest.raises(ErroDeValidacao, match="Escolaridade"):
        ler_rais_sc(caminho, None)


def test_estoque_rais_por_recorte(tmp_path):
    from src.rais import estoque_rais

    cbo = tmp_path / "cbo.csv"
    cbo.write_text(
        "cbo2002ocupação,descricao,macrofamilia,nivel_qualificacao,lideranca,justificativa\n"
        "784205,Alimentador,Produção industrial,Básico,False,\n"
    )
    v = pd.DataFrame({
        "chave_municipal": ["420540"] * 5,
        "ativo_31dez": [1, 1, 0, 0, 1],
        "escolaridade": [7, -1, 5, 9, 3],
        "motivo_desligamento": [0, 0, 11, 31, 0],   # 31 = transferência → fora
        "tempo_emprego_meses": [30.0, 2.0, 5.2, 3.0, 1.0],
        "cbo": ["784205", "784205", "784205", "784205", "999999"],
        "subclasse": ["2512800", "2512800", "2512800", "2512800", "4771701"],
    })
    e = estoque_rais(v, destino=tmp_path / "e.parquet", caminho_cbo=str(cbo))
    met = e[e.secao_industrial == "Indústrias de Transformação"].iloc[0]
    assert met.setor == "Metalurgia e produtos de metal"
    assert met.macrofamilia_cbo == "Produção industrial"
    assert (met.estoque_31dez, met.estoque_escolaridade_informada, met.estoque_medio_ou_mais) == (2, 1, 1)
    assert (met.desligados_rais, met.desligados_precoce) == (1, 1)
    com = e[e.secao_industrial.str.startswith("Comércio")].iloc[0]
    assert pd.isna(com.macrofamilia_cbo) and com.nivel_qualificacao == "Não informado"
    assert com.setor == com.secao_industrial and com.estoque_31dez == 1
    assert (tmp_path / "e.parquet").exists()
