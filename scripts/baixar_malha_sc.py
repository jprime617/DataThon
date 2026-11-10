"""Baixa a malha municipal de Santa Catarina para o mapa coroplético (R7.2).

O mapa do dashboard colore cada município pelo `saldo_por_10k` e precisa de uma
malha GeoJSON cujas *features* casem com a `municipio` da tabela agregada — a
Chave_Municipal de **6 dígitos**. A API de malhas do IBGE entrega os 295
municípios de SC identificados pelo código IBGE de **7 dígitos** (`codarea`), do
qual o 7º é verificador; este script baixa a malha, reescreve a propriedade de
identificação para a chave de 6 dígitos que o dashboard espera e **rebobina os
anéis dos polígonos** para a orientação que o Plotly exige (ver abaixo).

Orientação dos anéis
--------------------
O RFC 7946 manda que o anel externo de um polígono seja **anti-horário**, e é
assim que o IBGE entrega. O Plotly desenha mapas com o `d3-geo`, que usa
geometria esférica e a convenção **oposta**: para ele, um anel anti-horário
descreve *todo o globo menos aquela área*. O efeito é inconfundível — o mapa
inteiro fica pintado de uma cor só e cada município aparece como um buraco.
Por isso invertemos a orientação aqui, uma vez, ao gerar o arquivo.

Uso::

    python scripts/baixar_malha_sc.py

Grava `dashboard/geo/sc_municipios.geojson`. É um artefato de apresentação, não
uma etapa do pipeline: rode uma vez e versione o resultado.
"""

from __future__ import annotations

import gzip
import json
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "dashboard" / "geo" / "sc_municipios.geojson"

# Malha de SC (UF 42) subdividida por município, qualidade intermediária — o
# melhor equilíbrio entre fidelidade do contorno e tamanho do arquivo para uma
# conta de estudante (R9.4).
URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/42"
    "?formato=application/vnd.geo+json"
    "&intrarregiao=municipio"
    "&qualidade=intermediaria"
)

# Propriedade que o dashboard usa como chave das features (`CHAVE_GEOJSON`).
CHAVE = "chave_municipal"

# Número de municípios de Santa Catarina — serve de sanidade sobre o download.
MUNICIPIOS_SC = 295


def _area_assinada(anel: list) -> float:
    """Área assinada do anel pela fórmula do cadarço (positiva = anti-horário)."""
    soma = 0.0
    for (x1, y1), (x2, y2) in zip(anel, anel[1:]):
        soma += x1 * y2 - x2 * y1
    return soma / 2


def _rebobinar(geometria: dict) -> None:
    """Inverte os anéis para a convenção do d3-geo: externo horário.

    Modifica a geometria no lugar. O anel externo passa a ter área assinada
    negativa (horário) e os buracos, positiva (anti-horário) — o inverso do
    RFC 7946, que é o que o Plotly espera.
    """

    def corrigir(poligono: list) -> list:
        externo, *buracos = poligono
        if _area_assinada(externo) > 0:
            externo = externo[::-1]
        buracos = [b if _area_assinada(b) < 0 else b[::-1] for b in buracos]
        return [externo, *buracos]

    if geometria["type"] == "Polygon":
        geometria["coordinates"] = corrigir(geometria["coordinates"])
    elif geometria["type"] == "MultiPolygon":
        geometria["coordinates"] = [
            corrigir(poligono) for poligono in geometria["coordinates"]
        ]


def main() -> int:
    print(f"Baixando a malha de SC do IBGE…\n  {URL}")
    with urllib.request.urlopen(URL, timeout=120) as resposta:
        bruto = resposta.read()

    # O serviço responde comprimido mesmo sem negociação, e `urlopen` não
    # descomprime sozinho; identificamos o gzip pelos dois bytes mágicos.
    if bruto[:2] == b"\x1f\x8b":
        bruto = gzip.decompress(bruto)
    malha = json.loads(bruto.decode("utf-8"))

    features = malha.get("features", [])
    if len(features) != MUNICIPIOS_SC:
        print(
            f"AVISO: a malha veio com {len(features)} features; "
            f"esperado {MUNICIPIOS_SC} municípios de SC.",
            file=sys.stderr,
        )

    # `codarea` é o código IBGE de 7 dígitos; a chave comum com o CAGED são os
    # 6 primeiros (o 7º é verificador) — mesma regra de `chave_municipal_ibge`.
    convertidas = 0
    for feature in features:
        propriedades = feature.setdefault("properties", {})
        codigo = str(propriedades.get("codarea", "")).strip()
        if len(codigo) == 7 and codigo.isdecimal():
            propriedades[CHAVE] = codigo[:6]
            convertidas += 1
        # Orientação que o Plotly/d3-geo exige (ver docstring do módulo).
        _rebobinar(feature["geometry"])

    if convertidas != len(features):
        print(
            f"AVISO: {len(features) - convertidas} feature(s) sem código IBGE "
            "válido não receberam chave municipal.",
            file=sys.stderr,
        )

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(malha, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tamanho_kb = DESTINO.stat().st_size / 1024
    print(
        f"Malha gravada em {DESTINO.relative_to(RAIZ)} "
        f"({convertidas} municípios, {tamanho_kb:.0f} KB, anéis externos no "
        f"sentido horário)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
