"""Construtores puros de figuras Plotly do dashboard (sem Streamlit, sem I/O).

Cada ``construir_*`` recebe DataFrames já reagregados por `comum.agregar_metricas`
e devolve uma ``go.Figure``; em falta de dados devolve uma figura de
*empty-state* em vez de levantar. Títulos são a pergunta que o gráfico
responde; números no hover vêm formatados em pt-BR, sempre com o ``n``.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from dashboard import comum as c

ALTURA_PADRAO = 440


def _folga_x(valores, folga: float = 0.28) -> list[float]:
    """Faixa do eixo x com folga para os rótulos de texto fora das barras."""
    serie = pd.Series(valores, dtype="float64").dropna()
    if serie.empty:
        return [0, 1]
    minimo, maximo = min(0.0, float(serie.min())), max(0.0, float(serie.max()))
    largura = (maximo - minimo) or 1.0
    return [minimo - (folga * largura if minimo < 0 else 0), maximo + (folga * largura if maximo > 0 else 0)]


def _layout(figura: go.Figure, titulo: str, altura: int = ALTURA_PADRAO, **extras) -> go.Figure:
    c.registrar_template()
    figura.update_layout(title={"text": titulo}, height=altura, font={"size": 15}, **extras)
    return figura


# --- Mapa ---------------------------------------------------------------------

# Métrica do mapa → (escala, centro). Métricas com sinal usam a escala
# divergente centrada no neutro; taxas de tensão usam a escala sequencial.
ESCALAS_MAPA = {
    c.M_SALDO_10K: ("divergente", 0.0),
    c.M_SALDO_REL: ("divergente", 0.0),
    c.M_GAP_SAL: ("divergente", 1.0),
    c.M_GAP_ESC: ("divergente", 0.0),
    c.M_SAIDA_VOL: ("tensao", None),
    c.M_ROT_DESC: ("tensao", None),
}
# Cada indicador tem a sua paleta, para a troca de filtro ficar evidente no mapa.
# Divergentes vão do "ruim" (esquerda) ao "bom" (direita); sequenciais, do claro ao escuro.
PALETAS_MAPA = {
    c.M_SALDO_10K: c.CLASSES_DIVERGENTE,
    c.M_SALDO_REL: c.CLASSES_DIVERGENTE,
    c.M_GAP_SAL: ["#8C510A", "#D8B365", "#F6E8C3", "#C7EAE5", "#5AB4AC", "#01665E"],
    c.M_GAP_ESC: ["#762A83", "#AF8DC3", "#E7D4E8", "#D9F0D3", "#7FBF7B", "#1B7837"],
    c.M_SAIDA_VOL: ["#FEE6CE", "#FDAE6B", "#E6550D", "#8C2D04"],
    c.M_ROT_DESC: ["#EFE3F5", "#C3A4D6", "#8E63B5", "#4A2377"],
}
COR_BOLHA = "rgba(20, 20, 20, 0.12)"
COR_BOLHA_BORDA = "rgba(20, 20, 20, 0.75)"
PERCENTIL_LIMITE_ESCALA = 90  # mais cor nas classes do meio; extremos saturam
COR_SEM_DADO = "#D9D9D9"
LIMITES_SC = ([-53.9, -48.1], [-29.4, -25.9])  # (lon, lat) com folga; o mapa sempre mostra o estado inteiro
COR_REALCE = "#C2185B"  # magenta: território filtrado


def _degraus(cores: list[str]) -> list[list]:
    """Escala Plotly em degraus: uma faixa sólida por classe."""
    n = len(cores)
    return [par for i, cor in enumerate(cores) for par in ([i / n, cor], [(i + 1) / n, cor])]


def _rotulos_classes(metrica: str, bordas: list[float]) -> list[str]:
    """Legenda em degraus: "até X" por classe e "mais que X" na última."""
    return [f"até {c.fmt_metrica(metrica, b)}" for b in bordas] + [f"mais que {c.fmt_metrica(metrica, bordas[-1])}"]


def construir_mapa(
    metricas: pd.DataFrame,
    geojson: dict | None,
    metrica: str,
    *,
    rotulo_territorio: str = c.COLUNA_NOME_MUNICIPIO,
    destaque: list[str] | tuple[str, ...] = (),
    bolhas: pd.DataFrame | None = None,
    altura: int = 400,
) -> go.Figure:
    """Coroplético por município, em classes, colorido pela `metrica` da unidade territorial.

    ``metricas`` traz uma linha por **município** com ``municipio`` (chave de 6
    dígitos), o rótulo da unidade (o próprio município, a micro ou a
    mesorregião — cada município é pintado com o valor da sua unidade), a
    métrica e ``movimentacoes``. Taxas de tensão usam 4 quantis na escala
    sequencial; métricas com sinal, 6 classes simétricas na divergente. Unidades
    sem amostra suficiente ficam em cinza; as de ``destaque`` ganham contorno magenta.
    ``bolhas`` (``municipio``, nome e ``movimentacoes``) acrescenta a segunda
    camada: um círculo por município, com área proporcional ao volume.
    """
    if geojson is None:
        return c.figura_vazia("Mapa indisponível: malha de municípios não encontrada.")
    if metricas is None or metricas.empty or metrica not in metricas.columns:
        return c.figura_vazia("Sem dados para o mapa nesta seleção.")

    escala, centro = ESCALAS_MAPA.get(metrica, ("divergente", 0.0))
    definicao = c.DEFINICOES[metrica]
    validas = metricas[metricas[c.M_AMOSTRA_OK] & metricas[metrica].notna()]
    insuficientes = metricas[~metricas.index.isin(validas.index)]

    def _hover(dados: pd.DataFrame) -> list[str]:
        return [
            f"<b>{rot}</b><br>{definicao.rotulo}: {c.fmt_metrica(metrica, v)}"
            f"<br>n = {c.fmt_int(n)} movimentações"
            + ("" if ok else "<br><i>amostra insuficiente</i>")
            for rot, v, n, ok in zip(dados[rotulo_territorio], dados[metrica],
                                     dados[c.M_MOV], dados[c.M_AMOSTRA_OK])
        ]

    figura = go.Figure()
    if not insuficientes.empty:
        figura.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.chave_municipal",
            locations=insuficientes[c.COLUNA_MUNICIPIO].astype(str),
            z=[0] * len(insuficientes), colorscale=[[0, COR_SEM_DADO], [1, COR_SEM_DADO]],
            showscale=False, showlegend=True, marker_line_width=0.3, marker_line_color="white",
            text=_hover(insuficientes), hoverinfo="text",
            customdata=insuficientes[rotulo_territorio].astype(str),
            name="Dado inexistente (amostra insuficiente)",
        ))
    if not validas.empty:
        valores = validas[metrica].astype(float)
        if escala == "divergente":
            desvio = (valores - centro).abs()
            limite = float(desvio.quantile(PERCENTIL_LIMITE_ESCALA / 100)) or float(desvio.max()) or 1.0
            zmin, zmax = centro - limite, centro + limite
            cores = PALETAS_MAPA.get(metrica, c.CLASSES_DIVERGENTE)
            passo = (zmax - zmin) / len(cores)
            bordas = [zmin + passo * (i + 1) for i in range(len(cores) - 1)]
            z, ticks = valores, [zmin + passo * (i + 0.5) for i in range(len(cores))]
        else:
            bordas = sorted(set(float(valores.quantile(q)) for q in (0.25, 0.5, 0.75)))
            cores = PALETAS_MAPA.get(metrica, c.CLASSES_SEQUENCIAL)[-(len(bordas) + 1):]
            z = valores.map(lambda v: sum(v > b for b in bordas))
            zmin, zmax = -0.5, len(cores) - 0.5
            ticks = list(range(len(cores)))
        figura.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.chave_municipal",
            locations=validas[c.COLUNA_MUNICIPIO].astype(str), z=z,
            zmin=zmin, zmax=zmax, colorscale=_degraus(cores),
            marker_line_width=0.3, marker_line_color="white",
            text=_hover(validas), hoverinfo="text",
            customdata=validas[rotulo_territorio].astype(str), name=definicao.rotulo,
            colorbar={"title": {"text": "Legenda", "side": "top"}, "orientation": "h",
                      "x": 0, "xanchor": "left", "y": -0.02, "yanchor": "top", "len": 1, "thickness": 12,
                      "tickvals": ticks, "ticktext": _rotulos_classes(metrica, bordas), "outlinewidth": 0},
        ))
    alvo = metricas[metricas[rotulo_territorio].astype(str).isin([str(d) for d in destaque])]
    if not alvo.empty:
        # ponytail: contorna cada município do território (não a fronteira dissolvida);
        # dissolver exigiria shapely/geopandas.
        figura.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.chave_municipal",
            locations=alvo[c.COLUNA_MUNICIPIO].astype(str), z=[0] * len(alvo),
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker_line_width=2, marker_line_color=COR_REALCE, hoverinfo="skip",
            customdata=alvo[rotulo_territorio].astype(str), name="Território filtrado", showlegend=True,
        ))
    if bolhas is not None and not bolhas.empty:
        centros = centroides(geojson)
        b = bolhas[bolhas[c.COLUNA_MUNICIPIO].astype(str).isin(centros) & (bolhas[c.M_MOV] > 0)]
        if not b.empty:
            lon, lat = zip(*(centros[str(m)] for m in b[c.COLUNA_MUNICIPIO]))
            figura.add_trace(go.Scattergeo(
                lon=lon, lat=lat, mode="markers", name="Volume de movimentações (tamanho do círculo)",
                marker={"size": b[c.M_MOV], "sizemode": "area", "sizeref": 2 * float(b[c.M_MOV].max()) / 38 ** 2,
                        "sizemin": 2, "color": COR_BOLHA, "line": {"width": 1.2, "color": COR_BOLHA_BORDA}},
                text=[f"<b>{n}</b><br>{c.fmt_int(v)} movimentações"
                      for n, v in zip(b[c.COLUNA_NOME_MUNICIPIO], b[c.M_MOV])],
                hoverinfo="text", customdata=b[rotulo_territorio if rotulo_territorio in b else c.COLUNA_NOME_MUNICIPIO].astype(str),
            ))
    figura.update_geos(visible=False, bgcolor="rgba(0,0,0,0)", lonaxis_range=LIMITES_SC[0], lataxis_range=LIMITES_SC[1])
    return _layout(figura, f"{definicao.rotulo} por território", altura,
                   margin={"l": 0, "r": 0, "t": 50, "b": 90}, dragmode=False,
                   legend={"orientation": "h", "x": 0, "y": -0.2, "yanchor": "top", "font": {"size": 13}})


def centroides(geojson: dict) -> dict[str, tuple[float, float]]:
    """Chave municipal → (lon, lat): média dos vértices do maior anel do município."""
    centros = {}
    for f in geojson.get("features", []):
        g = f["geometry"]
        poligonos = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        anel = max((p[0] for p in poligonos), key=len)
        centros[str(f["properties"]["chave_municipal"])] = (
            sum(x for x, _ in anel) / len(anel), sum(y for _, y in anel) / len(anel))
    return centros


# --- Série mensal ---------------------------------------------------------------


def construir_serie_mensal(mensal: pd.DataFrame, titulo: str = "Como evoluiu: admissões, desligamentos e saldo") -> go.Figure:
    """Barras de admissões/desligamentos e linha do saldo por mês."""
    if mensal is None or mensal.empty:
        return c.figura_vazia("Sem dados mensais nesta seleção.")
    dados = mensal.assign(_ordem=mensal[c.COLUNA_MES].astype(str)).sort_values("_ordem")
    x = [c.rotulo_mes(m) for m in dados[c.COLUNA_MES]]
    figura = go.Figure()
    figura.add_bar(x=x, y=dados[c.COLUNA_ADMISSOES], name="Admissões", marker_color=c.COR_EXPANSAO,
                   hovertemplate="%{x}: %{y:,.0f} admissões<extra></extra>")
    figura.add_bar(x=x, y=-dados[c.COLUNA_DESLIGAMENTOS], name="Desligamentos", marker_color=c.COR_TENSAO,
                   marker_pattern_shape="/", customdata=dados[c.COLUNA_DESLIGAMENTOS],
                   hovertemplate="%{x}: %{customdata:,.0f} desligamentos<extra></extra>")
    figura.add_scatter(x=x, y=dados[c.M_SALDO], name="Saldo", mode="lines+markers",
                       line={"color": "#E69F00", "width": 3}, marker={"symbol": "diamond", "size": 10, "line": {"width": 1, "color": "white"}},
                       hovertemplate="%{x}: saldo %{y:,.0f}<extra></extra>")
    figura.add_hline(y=0, line_color=c.COR_NEUTRA, line_width=1)
    return _layout(figura, titulo, 400, barmode="relative",
                   legend={"orientation": "h", "y": -0.15}, yaxis_title="Movimentações (desligamentos abaixo de zero)")


# --- Matriz Dinamismo × Tensão --------------------------------------------------


def construir_matriz(matriz: pd.DataFrame, rotulo: pd.Series) -> go.Figure:
    """Bolhas Dinamismo × Tensão, um símbolo e uma cor por quadrante."""
    if matriz is None or matriz.empty:
        return c.figura_vazia("Nenhuma unidade com amostra suficiente (≥ 100 movimentações).")
    figura = go.Figure()
    tamanho_ref = float(matriz[c.M_MOV].max()) or 1.0
    for nome_q in c.QUADRANTES:
        parte = matriz[matriz["quadrante"] == nome_q]
        if parte.empty:
            continue
        rot = rotulo.loc[parte.index]
        figura.add_scatter(
            x=parte["dinamismo"], y=parte["tensao"], mode="markers", name=nome_q,
            marker={"size": 12 + 48 * (parte[c.M_MOV] / tamanho_ref) ** 0.5,
                    "color": c.CORES_QUADRANTE[nome_q], "opacity": 0.75, "line": {"width": 1, "color": "white"}},
            customdata=list(zip(rot, [c.fmt_int(v) for v in parte[c.M_MOV]],
                                [c.fmt_pct(v) for v in parte[c.M_SAIDA_VOL]],
                                [c.fmt_gap(v) for v in parte[c.M_GAP_SAL]],
                                parte["motor"])),
            hovertemplate=("<b>%{customdata[0]}</b><br>n = %{customdata[1]} movimentações"
                           "<br>saem a pedido: %{customdata[2]} · salário de entrada: %{customdata[3]} de quem saiu"
                           "<extra>%{fullData.name}</extra>"),
        )
    figura.add_hline(y=0, line_color=c.COR_NEUTRA, line_dash="dot")
    figura.add_vline(x=0, line_color=c.COR_NEUTRA, line_dash="dot")
    for texto, q in c.QUADRANTES.items():  # cada rótulo no seu canto (cresce → direita; perde → em cima)
        x, y = int(q.cresce), int(q.perde)
        figura.add_annotation(xref="paper", yref="paper", x=x, y=y, text=f"<b>{texto}</b>",
                              showarrow=False, xanchor="right" if x else "left",
                              yanchor="top" if y else "bottom", font={"size": 14, "color": c.CORES_QUADRANTE[texto]})
    # Eixos em palavras: o valor numérico (z-score) é detalhe técnico, fica na Metodologia.
    return _layout(figura, "Quem precisa de atenção: crescimento × perda de gente", 560,
                   xaxis={"title": "cresce pouco  →  cresce muito", "showticklabels": False},
                   yaxis={"title": "segura a equipe  →  perde a equipe", "showticklabels": False},
                   legend={"orientation": "h", "y": -0.12})


# --- Causa raiz -------------------------------------------------------------------


def construir_salario_por_categoria(medianas: pd.DataFrame, categoria: str, titulo: str) -> go.Figure:
    """Barras pareadas: mediana de admissão × de desligamento por categoria."""
    if medianas is None or medianas.empty:
        return c.figura_vazia("Sem salários suficientes nesta seleção.")
    dados = medianas[(medianas["n_admissao"] >= c.MIN_SALARIOS) & (medianas["n_desligamento"] >= c.MIN_SALARIOS)]
    if dados.empty:
        return c.figura_vazia(f"Nenhuma categoria com ≥ {c.MIN_SALARIOS} salários de cada lado.")
    figura = go.Figure()
    for coluna, n, nome, cor, padrao in (
        ("mediana_admissao", "n_admissao", "Admitidos", c.COR_EXPANSAO, ""),
        ("mediana_desligamento", "n_desligamento", "Desligados", c.COR_TENSAO, "/"),
    ):
        figura.add_bar(
            y=dados[categoria].astype(str), x=dados[coluna], name=nome, orientation="h",
            marker_color=cor, marker_pattern_shape=padrao,
            text=[c.fmt_brl(v) for v in dados[coluna]], textposition="outside",
            customdata=[c.fmt_int(v) for v in dados[n]],
            hovertemplate="%{y}<br>" + nome + ": %{text} (n = %{customdata})<extra></extra>",
        )
    figura.update_traces(cliponaxis=False)
    return _layout(figura, titulo, 140 + 60 * len(dados), barmode="group",
                   xaxis={"title": "Mediana do salário (R$)", "tickformat": ",.0f",
                          "range": _folga_x(pd.concat([dados["mediana_admissao"], dados["mediana_desligamento"]]))},
                   legend={"orientation": "h", "y": -0.12}, yaxis={"autorange": "reversed"})


def construir_gap_escolaridade(metricas: pd.DataFrame, categoria: str) -> go.Figure:
    """Gap de escolaridade (admitidos − desligados) por categoria, com amostra."""
    dados = metricas[metricas[c.M_AMOSTRA_OK] & metricas[c.M_GAP_ESC].notna()] if metricas is not None else None
    if dados is None or dados.empty:
        return c.figura_vazia("Sem amostra suficiente para o gap de escolaridade.")
    dados = dados.sort_values(c.M_GAP_ESC)
    cores = [c.COR_TENSAO if v < 0 else c.COR_EXPANSAO for v in dados[c.M_GAP_ESC]]
    figura = go.Figure(go.Bar(
        y=dados[categoria].astype(str), x=dados[c.M_GAP_ESC], orientation="h", marker_color=cores,
        text=[c.fmt_metrica(c.M_GAP_ESC, v) for v in dados[c.M_GAP_ESC]], textposition="outside",
        customdata=[c.fmt_int(v) for v in dados[c.M_MOV]],
        hovertemplate="%{y}<br>gap %{text} níveis (n = %{customdata})<extra></extra>",
    ))
    figura.add_vline(x=0, line_color=c.COR_NEUTRA)
    figura.update_traces(cliponaxis=False)
    return _layout(figura, "Quem entra tem mais ou menos estudo do que quem sai?", 140 + 42 * len(dados),
                   xaxis={"title": "Admitidos − desligados (níveis)",
                          "range": _folga_x(dados[c.M_GAP_ESC], 0.45)})


def construir_dispersao(
    metricas: pd.DataFrame, rotulo: pd.Series, x: str, y: str, titulo: str, *, tamanho: bool = True
) -> go.Figure:
    """Dispersão genérica entre duas métricas, com n no hover e tamanho = volume."""
    if metricas is None or metricas.empty:
        return c.figura_vazia("Sem unidades com amostra suficiente.")
    dados = metricas.dropna(subset=[x, y])
    if dados.empty:
        return c.figura_vazia("Sem unidades com as duas métricas disponíveis.")
    ref = float(dados[c.M_MOV].max()) or 1.0
    rot_x = c.DEFINICOES[x].rotulo if x in c.DEFINICOES else x
    rot_y = c.DEFINICOES[y].rotulo if y in c.DEFINICOES else y
    figura = go.Figure(go.Scatter(
        x=dados[x], y=dados[y], mode="markers",
        marker={"size": (10 + 40 * (dados[c.M_MOV] / ref) ** 0.5) if tamanho else 10,
                "color": c.COR_DESTAQUE, "opacity": 0.6, "line": {"width": 1, "color": "white"}},
        customdata=list(zip(rotulo.loc[dados.index], [c.fmt_metrica(x, v) if x in c.DEFINICOES else c.fmt_num(v, 3) for v in dados[x]],
                            [c.fmt_metrica(y, v) for v in dados[y]], [c.fmt_int(v) for v in dados[c.M_MOV]])),
        hovertemplate=f"<b>%{{customdata[0]}}</b><br>{rot_x}: %{{customdata[1]}}<br>{rot_y}: %{{customdata[2]}}"
                      "<br>n = %{customdata[3]}<extra></extra>",
    ))
    return _layout(figura, titulo, 460, xaxis_title=rot_x, yaxis_title=rot_y)


# --- Ocupações (IA) ---------------------------------------------------------------


def construir_treemap(metricas: pd.DataFrame) -> go.Figure:
    """Treemap macrofamília → nível; área = movimentações, cor = saída voluntária."""
    if metricas is None or metricas.empty:
        return c.figura_vazia("Sem movimentações nesta seleção.")
    dados = metricas[metricas[c.M_MOV] > 0]
    ids, rotulos, pais, valores, cores, textos = [], [], [], [], [], []
    for macro, g in dados.groupby(c.COLUNA_MACROFAMILIA_CBO, observed=True):
        mov = g[c.M_MOV].sum()
        desl = g[c.COLUNA_DESLIGAMENTOS].sum()
        saida = g[c.COLUNA_DESLIGAMENTOS_A_PEDIDO].sum() / desl if desl else float("nan")
        ids.append(str(macro)); rotulos.append(str(macro)); pais.append(""); valores.append(mov); cores.append(saida)
        textos.append(f"{c.fmt_int(mov)} movimentações · saída voluntária {c.fmt_pct(saida)}")
        for _, linha in g.iterrows():
            ids.append(f"{macro}/{linha[c.COLUNA_NIVEL_QUALIFICACAO]}")
            rotulos.append(str(linha[c.COLUNA_NIVEL_QUALIFICACAO])); pais.append(str(macro))
            valores.append(linha[c.M_MOV]); cores.append(linha[c.M_SAIDA_VOL])
            textos.append(f"{c.fmt_int(linha[c.M_MOV])} movimentações · saída voluntária "
                          f"{c.fmt_pct(linha[c.M_SAIDA_VOL])}" + ("" if linha[c.M_AMOSTRA_OK] else " · amostra insuficiente"))
    figura = go.Figure(go.Treemap(
        ids=ids, labels=rotulos, parents=pais, values=valores, branchvalues="total",
        marker={"colors": cores, "colorscale": c.ESCALA_TENSAO, "showscale": True,
                "colorbar": {"title": {"text": "Saída voluntária"}, "tickformat": ".0%"}},
        text=textos, hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>",
        texttemplate="<b>%{label}</b><br>%{value:,.0f}", textfont={"size": 15, "color": "#1B2430"},
        root={"color": "rgba(0,0,0,0)"}, pathbar={"visible": False},
    ))
    return _layout(figura, "Que profissional gira: macrofamília (IA) → nível de qualificação", 560,
                   margin={"l": 0, "r": 0, "t": 50, "b": 0})


# --- Barras simples ---------------------------------------------------------------


def construir_barras(metricas: pd.DataFrame, categoria: str, metrica: str, titulo: str, *, limite: int = 15) -> go.Figure:
    """Barras horizontais de uma métrica por categoria (cinza = amostra insuficiente)."""
    if metricas is None or metricas.empty:
        return c.figura_vazia("Sem dados nesta seleção.")
    dados = metricas.dropna(subset=[metrica]).sort_values(metrica, ascending=False).head(limite)
    if dados.empty:
        return c.figura_vazia("Sem dados nesta seleção.")
    sinal = c.DEFINICOES[metrica].formato in ("int", "num1", "num2", "pp")
    cores = [
        c.COR_NEUTRA if not ok else (c.COR_TENSAO if (sinal and v < 0) or (not sinal) else c.COR_EXPANSAO)
        for v, ok in zip(dados[metrica], dados[c.M_AMOSTRA_OK])
    ] if sinal else [c.COR_TENSAO if ok else c.COR_NEUTRA for ok in dados[c.M_AMOSTRA_OK]]
    figura = go.Figure(go.Bar(
        y=dados[categoria].astype(str), x=dados[metrica], orientation="h", marker_color=cores,
        text=[c.fmt_metrica(metrica, v) for v in dados[metrica]], textposition="outside",
        customdata=[c.fmt_int(v) for v in dados[c.M_MOV]],
        hovertemplate="%{y}<br>%{text} (n = %{customdata})<extra></extra>",
    ))
    figura.update_traces(cliponaxis=False)
    return _layout(figura, titulo, 140 + 38 * len(dados), yaxis={"autorange": "reversed"},
                   xaxis={"title": c.DEFINICOES[metrica].rotulo, "range": _folga_x(dados[metrica], 0.45)})


def construir_funil(etapas: list) -> go.Figure:
    """Funil do pipeline, de cima para baixo na ordem do processo (BUG-02).

    Aceita `narrativa.EtapaFunil` (rótulo, valor, perda, motivo) ou pares
    (rótulo, valor). Cada barra mostra o valor e, quando houve queda, quanto saiu.
    """
    if not etapas:
        return c.figura_vazia("Metadados indisponíveis.")
    rotulos = [getattr(e, "rotulo", None) or e[0] for e in etapas]
    valores = [getattr(e, "valor", None) if hasattr(e, "valor") else e[1] for e in etapas]
    perdas = [getattr(e, "perda", 0) for e in etapas]
    textos = [c.fmt_int(v) + (f"  (−{c.fmt_int(p)})" if p else "") for v, p in zip(valores, perdas)]
    cores = [c.COR_DESTAQUE, c.COR_DESTAQUE, "#5B8DB8", c.COR_EXPANSAO, c.COR_EXPANSAO]
    figura = go.Figure(go.Funnel(
        y=rotulos, x=valores, text=textos, textinfo="text", textposition="inside",
        marker={"color": cores[: len(etapas)]}, hoverinfo="y+text",
    ))
    figura.update_yaxes(categoryorder="array", categoryarray=rotulos, autorange="reversed")
    return _layout(figura, "Do arquivo bruto à indústria: volume em cada etapa", 340)
