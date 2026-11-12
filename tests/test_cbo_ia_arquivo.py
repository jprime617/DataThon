"""M2.C1: `ClienteArquivo` junta as respostas coladas da IA paga, sem chamar API."""

import json

import pytest

from src.cbo_ia import ClienteArquivo, classificar_lote, criar_cliente_llm
from src.erros import ErroDeValidacao


def _pasta(tmp_path, respostas: dict[str, str], prompts=("lote_01", "lote_02")):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "respostas").mkdir()
    for nome in prompts:
        (tmp_path / "prompts" / f"{nome}.txt").write_text("prompt", encoding="utf-8")
    for nome, texto in respostas.items():
        (tmp_path / "respostas" / f"{nome}.json").write_text(texto, encoding="utf-8")
    return tmp_path


def test_junta_dois_arquivos_e_classificar_lote_filtra_o_lote(tmp_path):
    pasta = _pasta(tmp_path, {
        "lote_01": json.dumps({"784205": {"macrofamilia": "Operação de linha e processo", "nivel": "Básico",
                                          "justificativa": ""}}),
        # Texto e cerca ```json em volta são tolerados.
        "lote_02": "Aqui está:\n```json\n" + json.dumps({"411010": {"macrofamilia": "Administrativo e comercial",
                                                                   "nivel": "Qualificado", "justificativa": ""}})
                   + "\n```",
    })
    cliente = ClienteArquivo(pasta, modelo="modelo-x")
    assert set(json.loads(cliente.classificar("p", timeout=1))) == {"784205", "411010"}
    assert cliente._modelo == "modelo-x"
    resultado = classificar_lote(["411010"], cliente)
    assert list(resultado) == ["411010"]
    assert resultado["411010"]["macrofamilia"] == "Administrativo e comercial"


def test_lote_faltante_da_erro_listando_os_lotes(tmp_path):
    pasta = _pasta(tmp_path, {"lote_01": "{}"}, prompts=("lote_01", "lote_02", "lote_03"))
    with pytest.raises(ErroDeValidacao, match="lote_02, lote_03"):
        ClienteArquivo(pasta)


def test_resposta_sem_json_da_erro(tmp_path):
    pasta = _pasta(tmp_path, {"lote_01": json.dumps({"1": {"macrofamilia": "a"}}), "lote_02": "cortou no meio {\"4110"})
    with pytest.raises(ErroDeValidacao, match="lote_02.json"):
        ClienteArquivo(pasta)


def test_provedor_arquivo_nao_exige_chave(tmp_path, monkeypatch):
    (tmp_path / "ia_cbo").mkdir()
    _pasta(tmp_path / "ia_cbo", {"lote_01": json.dumps({"1": {"macrofamilia": "a"}}),
                                 "lote_02": json.dumps({"2": {"macrofamilia": "b"}})})
    monkeypatch.chdir(tmp_path)
    cliente = criar_cliente_llm(env={"LLM_PROVIDER": "arquivo", "LLM_MODELO_MANUAL": "chat-pago"})
    assert isinstance(cliente, ClienteArquivo) and cliente._modelo == "chat-pago"


def test_concordancia_do_modo_arquivo_compara_com_o_gemini(tmp_path):
    """M2.C2: a rodada 2 é o CSV anterior (Gemini), não a releitura do mesmo arquivo."""
    import pandas as pd

    from src.cbo_ia import NOME_CSV_REFERENCIA, classificar_cbos

    def resp(familia: str) -> dict:
        return {"macrofamilia": familia, "nivel": "Qualificado", "justificativa": "Revisão humana: teste."}

    ia = tmp_path / "ia_cbo"
    ia.mkdir()
    pasta = _pasta(ia, {"lote_01": json.dumps({"411010": resp("Administrativo e comercial"),
                                               "784205": resp("Logística e transporte")})},
                   prompts=("lote_01",))
    saida = tmp_path / "dp"
    saida.mkdir()
    pd.DataFrame({"cbo2002ocupação": ["411010", "784205"], "descricao": ["a", "b"],
                  "macrofamilia": ["Administrativo e comercial", "Operação de linha e processo"],
                  "nivel_qualificacao": ["Qualificado", "Qualificado"], "lideranca": [False, False],
                  "justificativa": ["", ""]}).to_csv(saida / NOME_CSV_REFERENCIA, index=False)
    base = pd.DataFrame({"cbo2002ocupação": ["411010", "784205", "784205"]})
    r = classificar_cbos(base, ClienteArquivo(pasta, modelo="pago"), destino_csv=str(saida / "cbo_macrofamilias.csv"))
    meta = json.loads((saida / "cbo_macrofamilias.csv.meta.json").read_text(encoding="utf-8"))
    assert meta["concordancia_familia"] == 0.5 and meta["cbos_comparados"] == 2
    assert NOME_CSV_REFERENCIA in meta["comparacao"] and "ia_cbo" in meta["nota"]
    assert meta["provedor"] == "ClienteArquivo" and meta["modelo"] == "pago"
    divergencias = pd.read_csv(saida / "cbo_divergencias.csv", dtype=str)
    assert list(divergencias["cbo2002ocupação"]) == ["784205"]
    assert r.mapeamento["411010"] == "Administrativo e comercial"
