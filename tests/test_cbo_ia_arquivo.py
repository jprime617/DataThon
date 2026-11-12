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
