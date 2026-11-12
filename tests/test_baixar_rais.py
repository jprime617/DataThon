"""Testes das partes puras do download da RAIS (M4.C1): retomada e extração."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parent.parent / "scripts" / "baixar_rais.py"
_spec = importlib.util.spec_from_file_location("baixar_rais", _CAMINHO)
baixar_rais = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(baixar_rais)


def test_baixa_quando_nao_existe(tmp_path):
    assert baixar_rais.precisa_baixar(tmp_path / "x.7z", 10)


def test_pula_quando_tamanho_confere(tmp_path):
    f = tmp_path / "x.7z"
    f.write_bytes(b"0123456789")
    assert not baixar_rais.precisa_baixar(f, 10)


def test_rebaixa_quando_tamanho_diverge(tmp_path):
    f = tmp_path / "x.7z"
    f.write_bytes(b"01234")
    assert baixar_rais.precisa_baixar(f, 10)


def test_sem_tamanho_remoto_basta_existir(tmp_path):
    f = tmp_path / "x.7z"
    f.write_bytes(b"0")
    assert not baixar_rais.precisa_baixar(f, None)


def test_prefere_7z(monkeypatch, tmp_path):
    monkeypatch.setattr(baixar_rais.shutil, "which", lambda nome: f"/usr/bin/{nome}")
    cmd = baixar_rais.comando_extracao(tmp_path / "a.7z", tmp_path)
    assert cmd[0] == "7z"


def test_cai_para_bsdtar(monkeypatch, tmp_path):
    monkeypatch.setattr(
        baixar_rais.shutil, "which", lambda nome: "/usr/bin/bsdtar" if nome == "bsdtar" else None
    )
    cmd = baixar_rais.comando_extracao(tmp_path / "a.7z", tmp_path)
    assert cmd[:2] == ["bsdtar", "-xf"]


def test_sem_extrator_falha(monkeypatch, tmp_path):
    monkeypatch.setattr(baixar_rais.shutil, "which", lambda nome: None)
    with pytest.raises(RuntimeError):
        baixar_rais.comando_extracao(tmp_path / "a.7z", tmp_path)
