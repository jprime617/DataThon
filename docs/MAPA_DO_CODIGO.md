# Mapa do código — Raio-X da Indústria SC

Resumo para quem vai mexer no painel antes do pitch. Escrito no início do plano
`PLANO_CORRECOES_DATATHON.md` (branch `fix/banca`).

## Camadas

| Camada | Onde | O que faz |
|---|---|---|
| Ingestão e limpeza | `src/ingestao.py`, `src/limpeza.py`, `src/download.py` | Lê o Novo CAGED (MOV/FOR/EXC do FTP do MTE, set/24–ago/26), valida domínios, converte moeda e escolaridade (`limpeza.ESCOLARIDADE_ORDINAL`, 1–11). |
| Mapeamentos | `src/mapeamentos.py` | Mesorregião/microrregião por município, **setor por divisão CNAE** (`SETOR_POR_DIVISAO_TRANSFORMACAO`; desde o TAX-01, div. 29 = "Veículos automotores e autopeças" e div. 30 = "Construção naval e outros equipamentos de transporte"), faixas de escolaridade e nomes das 12 macrofamílias de CBO. |
| Métricas e agregação | `src/metricas.py`, `src/agregador.py` | `preparar_base` aplica o peso do consolidado (linha EXC = −1). `agregar` gera `caged_agregado.parquet` (município × seção/setor × macrofamília × nível × mês), `agregar_perfil` gera `caged_perfil.parquet` (com medianas salariais e faixa de escolaridade) e `montar_metadados` gera `metadados.json` (o funil). |
| IA (CBO → macrofamília) | `src/cbo_ia.py`, `ia_cbo/` | Prompts em 23 lotes (`ia_cbo/prompts`), respostas coladas do chat (`ia_cbo/respostas`, provedor `arquivo`). Saída: `data_processed/cbo_macrofamilias.csv` + `.meta.json`. A concordância é medida contra a classificação anterior do Gemini (`cbo_macrofamilias_gemini.csv`). As divergências vão para `cbo_divergencias.csv`. |
| Classificação final da CBO | `src/cbo_ia.py` (`mapeamento_final`, `desempatar`, `ler_overrides`), `ia_cbo/overrides.csv` | Depois da IA: regra de desempate entre as rodadas (TAX-04 P1) e overrides manuais (TAX-03). Saída `data_processed/cbo_classificacao_final.csv`, com a origem de cada decisão. Vale para o CAGED e para a RAIS. |
| Classificação pela API | `ia_cbo/classificar.py` | Repete a classificação pela API com os mesmos prompts do chat (TAX-06; não executado). |
| Benchmark SC × Brasil | `src/caged_brasil.py` | Relê os `.7z` nacionais → `data_processed/caged_brasil_secao.parquet` (ANA-04). |
| RAIS | `src/rais.py`, `scripts/baixar_rais.py` | Estoque em 31/12/2025 (`rais_estoque.parquet`), usado para rotatividade descontada e desligamento precoce. |
| Publicação | `src/azure_upload.py` | Sobe os agregados para o Blob (container `caged-agregado`). |
| Orquestração | `notebooks/01_pipeline.ipynb` | Roda tudo na ordem. Precisa dos microdados em `data/raw/caged/`. |
| Painel | `dashboard/app.py`, `dashboard/comum.py`, `dashboard/narrativa.py`, `dashboard/figuras.py`, `dashboard/paginas/*.py` | Streamlit. Lê do Blob e, se falhar, usa a cópia local em `data_processed/`. |

## Painel: onde fica cada coisa

**`dashboard/comum.py`** (≈1.600 linhas) concentra quase toda a regra de negócio do painel:
- carga dos artefatos, filtros (`Filtros`, `barra_lateral`, escopos `ESCOPO_INDUSTRIA`/`ESCOPO_ECONOMIA`);
- métricas derivadas (`agregar_metricas`, `_derivar`, `DEFINICOES`, constantes `M_*`, `MIN_MOVIMENTACOES=100`, `MIN_SALARIOS=30`, `LIMIAR_COMPRESSAO=0,95`);
- diagnóstico: `zscore` e `matriz_diagnostico` (quadrantes, causas, alavancas e limiares vêm de **`dashboard/regras.py`**, a fonte única de rótulos e regras, reexportada por `comum`);
- causas (`causas()`: Salarial, Qualificação e Retenção) e o motor de recomendações (`gerar_recomendacoes`, `ALAVANCA_*`);
- formatadores pt-BR (`fmt_num`, `fmt_pct`, `fmt_brl`, `fmt_gap`, `fmt_metrica`) e `delta_texto` (delta "vs SC/estado");
- cartões de KPI, CSS e tema dos gráficos.

**`dashboard/narrativa.py`** monta os textos calculados: a manchete (`resposta_principal`), os achados (`principais_achados`), as legendas do mapa e da série mensal, e os sinais e o guia por quadrante do Panorama.

**`dashboard/figuras.py`** constrói as figuras Plotly: mapa, série mensal, matriz, barras, treemap e funil (`construir_funil`).

**Páginas** (`dashboard/paginas/`):

| Página | Arquivo | Itens do plano que a tocam |
|---|---|---|
| Panorama ("Onde está o problema?") | `panorama.py` | NAR-02, NAR-03, NAR-05, TAX-01 (achados) |
| Quem precisa de atenção | `diagnostico.py` | NAR-01, NAR-03, ANA-03, BUG-01 (cartões com delta "vs SC") |
| Por que acontece | `causa_raiz.py` | ANA-01, ANA-02, DATA-01 |
| Que profissional falta | `ocupacoes.py` | TAX-03, TAX-04, TAX-05 |
| O que fazer | `recomendacoes.py` | REC-01 a REC-06, BUG-04 (custo) |
| Ficha do território | `ficha.py` | BUG-01, BUG-03, BUG-05 |
| Metodologia | `metodologia.py` | BUG-02 (funil), NAR-04, ENT-01 |
| Apresentação (oculta, com chave) | `apresentacao.py` | NAR-01 (contagem por quadrante) |

## Pipeline × painel: o que dá para mudar sem reprocessar

- O agregado tem **seção, setor, macrofamília, nível e mês por município**, mas **não tem divisão nem subclasse CNAE nem CBO**. A divisão 29 × 30 (TAX-01) e a razão salarial por CBO (ANA-01 P1) **exigem reprocessar** os microdados.
- Os microdados não vêm no repositório. Para reprocessar: `python -m src.download` (72 `.7z` do CAGED), `python scripts/baixar_rais.py`, `python -m src.rais && python -m src.rais --estoque`, `python -m src.caged24` e o notebook com `PULAR_UPLOAD=1`. Com 8 GB de RAM, a limpeza precisa de swap (o kernel morre sem ele).
- Renomear setor ou macrofamília, mudar quadrantes, causas, limiares e recomendações, e montar textos e o funil: tudo isso dá para fazer **na camada do painel**.
- Os rótulos de quadrante, causa e alavanca já são constantes em `comum.py`, mas há **strings soltas** que os repetem (ex.: `apresentacao.py:64`, docstrings e textos em `narrativa.py`).

## Testes

`pytest` na raiz (`pytest.ini`): 266 passaram e 6 foram pulados (contrato com dados reais), em ≈2 min.
Os do painel são `tests/test_dashboard_*.py`; os de regras de métrica, `tests/test_metricas_*.py` e `tests/test_agregador_*.py`.

## Deploy

Azure App Service (Linux, `startup.sh`), com deploy via `az webapp deploy` (`docs/COMO_RODAR.md`, seção de deploy). Não há CI. **A CLI `az` não está instalada neste ambiente.**
Repositório: `github.com/jprime617/DataThon`. Branch principal: `dashboard-v2` (tags `entrega-v1` e `entrega-v2`).
