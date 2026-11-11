# Planejamento — Datathon CDIA 2026
## Raio-X do Mercado de Trabalho e Vagas Industriais em Santa Catarina

> Documento vivo da equipe. Registra **o que** vamos fazer, **como** e **por quê**, antes de escrever código.
> Última atualização: 10/11/2026.

---

## 0. Resumo

**Pergunta central:** *Quais regiões e setores industriais de SC estão enfrentando apagão de mão de obra ou expansão acelerada, e como os indicadores de renda e escolaridade explicam esses gargalos?*

**Nossa resposta em uma frase (hipótese a confirmar):** a indústria catarinense gira muito e cresce pouco. O "apagão" aparece como **rotatividade e saída voluntária altas**, e não como falta de contratação. Ele é explicado em parte por **compressão salarial na reposição**: quem entra ganha menos do que quem sai, e a diferença cresce com a escolaridade.

**Entregáveis (repositório Git público + formulário):**
1. Notebooks/scripts com o pipeline completo e documentado.
2. Dashboard interativo em Python (Streamlit), com pelo menos 3 KPIs.
3. Pitch executivo de 3 minutos (slides).

**Banca:** especialistas de **empresas parceiras**. As recomendações falam com a empresa: o que ela pode fazer.

---

## 1. Decisões tomadas

| # | Tema | Decisão |
|---|---|---|
| D1 | Período | **Set/2024 a Ago/2026 (24 meses)**, em dois blocos: **anterior** (set/24 a ago/25) e **recente** (set/25 a ago/26, a mesma janela da base fornecida) |
| D2 | Escopo industrial | **Seções CNAE B, C, D, E, F** (critério IBGE/CNI), em **3 visões** + abertura da seção C em setores (ver §4.2) |
| D3 | Território | **Mesorregiões IBGE (6)** como visão principal, **microrregiões (20)** e **municípios (295)** para aprofundar |
| D4 | IA nos CBOs | Sem API: a classificação é feita **via Claude Code/chat**, com prompt versionado e resultado salvo em CSV. **Todos os 2.207 CBOs** presentes nos dados |
| D5 | Exclusões | Reconstruir a base pela regra oficial **MOV + FOR − EXC** a partir do FTP do MTE e **validar** contra a base fornecida e a série oficial |
| D6 | Estoque / RAIS | Puxar **RAIS 2024 e RAIS 2025** (vínculos, região Sul → SC) para obter o estoque por município × setor × CBO |
| D7 | Rotatividade | Usar a **definição oficial do MTE** (taxa descontada, ver §6) para comparar com as tabelas oficiais |
| D8 | Dashboard | **Streamlit + Plotly**, publicado no Streamlit Community Cloud |
| D9 | Recomendações | Voltadas a **ações das empresas** (salário, retenção, recrutamento, formação interna, automação), não centradas em uma instituição de ensino |

---

## 2. Fontes de dados

| Fonte | Conteúdo | Uso | Onde |
|---|---|---|---|
| **Novo CAGED – microdados** (MOV, FOR, EXC) | 1 linha por movimentação (admissão/desligamento), Brasil, mensal | Base principal, 24 meses | `ftp://ftp.mtps.gov.br/pdet/microdados/NOVO CAGED/AAAA/AAAAMM/` (~50 MB/mês compactado) |
| **Base fornecida** `Novo_Caged_MOV_Limpo.csv` | Microdados SC, set/25–ago/26 (3,4 mi linhas) | **Validação** do bloco recente | `fora_gh/` (fora do Git) |
| **RAIS 2024 e 2025** – vínculos | 1 linha por vínculo no ano, com situação em 31/12 | Estoque por município × CNAE × CBO, perfil do estoque, tempo de emprego | `ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/2025/RAIS_VINC_PUB_SUL.7z` (705 MB) e `/2024/` (681 MB) |
| **Tabelas oficiais do CAGED – set/2026** | Agregados publicados pelo MTE (série 2020–set/26 "com ajustes") | Estoque mensal por município e por UF, rotatividade oficial, benchmark Brasil por seção | `docs/docs_admissao/09-2026/3-tabelas_Setembro de 2026.xlsx` |
| **Municipios_SC_limpo.csv** | População (Censo 2022 e estimativa 2026), área, IDHM, PIB per capita, escolarização | Normalização (por 10 mil hab.) e correlações | `docs/` |
| **Dicionário de dados** | Layout e tabelas de códigos (CBO, CNAE, escolaridade etc.) | Decodificação e insumo da IA | `docs/Dicionario_de_dados.xlsx` |
| **IBGE Localidades** | Município → microrregião → mesorregião | Recorte territorial | `https://servicodados.ibge.gov.br/api/v1/localidades/estados/42/municipios` |
| **IBGE Malhas** | GeoJSON dos municípios de SC | Mapas | `https://servicodados.ibge.gov.br/api/v3/malhas/estados/42?intrarregiao=municipio&formato=application/vnd.geo+json` |
| **IBGE SIDRA – INPC** | Inflação mensal (tabela 1736, var. 44) | Deflacionar salários para preços de ago/2026 | `https://apisidra.ibge.gov.br/values/t/1736/n1/all/v/44/p/all` |

Todas as URLs foram testadas em 10/11/2026.

### Abas do xlsx oficial que vamos usar
| Aba | Conteúdo | Uso |
|---|---|---|
| Tabela 7.1 | Estoque/adm/desl/saldo mensal por **UF** (com ajustes) | Série de SC 2020–2026, validação estadual |
| Tabela 8.1 | Idem por **município** | Estoque municipal mensal (denominador), validação municipal |
| Tabela 6.1 | Idem por **seção CNAE – Brasil** | Benchmark SC × Brasil por seção |
| Tabelas 10 e 11 | **Taxa de rotatividade descontada** por seção (Brasil) e por UF | Referência metodológica e benchmark |
| Tabela 9 | Salário médio real de admissão e de desligamento (Brasil) | Contexto |

> Os CSVs em `docs/docs_admissao/` são exportações de abas deste mesmo xlsx. Vamos ler direto do xlsx, que é a fonte única.

---

## 3. Janela temporal

- **Dados:** set/2024 a ago/2026, pela competência da declaração.
- **Blocos de comparação:** `anterior` = set/24 a ago/25 · `recente` = set/25 a ago/26.
- **Por que 12 × 12:** mede **aceleração** ("expansão acelerada" pressupõe comparação) e neutraliza a sazonalidade (dezembro aparece nos dois blocos).
- **Contexto:** série oficial 2020–2026 (estoque mensal) só para mostrar a tendência de longo prazo e o pós-pandemia.
- **Dashboard:** seletor `Últimos 12 meses | 24 meses | Comparação entre os blocos`.

---

## 4. Recortes de análise

### 4.1 Território
- `mesorregiao` (6): Oeste Catarinense, Norte Catarinense, Serrana, Vale do Itajaí, Grande Florianópolis, Sul Catarinense.
- `microrregiao` (20) e `municipio` (295).
- **Chave de junção:** o CAGED e a RAIS usam o código IBGE de **6 dígitos**. O IBGE e a base de municípios usam **7 dígitos** (com dígito verificador). Regra: `cod6 = cod7 // 10`. Junção 100% testada.

### 4.2 Setores (CNAE)
`divisao = subclasse // 100000` (subclasse tem 7 dígitos; a seção B perde o zero à esquerda, mas a conta continua válida).

| Visão | Grupos |
|---|---|
| **V1 – Agrupada** | Transformação (C) · Construção (F) · Extrativa e Utilidades (B+D+E) |
| **V2 – Por seção** | B · C · D · E · F |
| **V3 – Indústria total** | B–F |
| **Setores da Transformação (C)** | ver abaixo |

| Setor (seção C) | Divisões CNAE | Polo em SC |
|---|---|---|
| Alimentos e bebidas | 10, 11 | Oeste (agroindústria) |
| Têxtil, confecção e calçados | 13, 14, 15 | Vale do Itajaí |
| Madeira, papel e móveis | 16, 17, 31 | Norte / Planalto (São Bento do Sul, Caçador) |
| Química, plástico e borracha | 19, 20, 21, 22 | Norte |
| Cerâmica e minerais não metálicos | 23 | Sul (Criciúma) |
| Metalurgia e produtos de metal | 24, 25 | Norte |
| Eletroeletrônico e máquinas elétricas | 26, 27 | Norte (Jaraguá do Sul / Joinville), Grande Florianópolis |
| Máquinas e equipamentos | 28, 33 | Norte |
| Veículos e equipamentos de transporte | 29, 30 | Norte |
| Outras indústrias de transformação | 12, 18, 32 | — |

As outras seções (comércio, serviços, agro) entram só como **referência** ("a indústria vs. o resto da economia").

### 4.3 Ocupações (CBO)
- `macrofamilia` e `nivel_qualificacao` gerados por IA (§8).
- Hierarquia oficial da CBO para validação: grande grupo (1º dígito), subgrupo principal (2), subgrupo (3), família (4).

### 4.4 Escolaridade (agrupada)
| Faixa | Códigos CAGED |
|---|---|
| Até fundamental incompleto | 1, 2, 3, 4 |
| Fundamental completo | 5 |
| Médio incompleto | 6 |
| Médio completo | 7 |
| Superior incompleto | 8 |
| Superior completo ou mais | 9, 10, 11, 80 |

---

## 5. Pipeline de dados

### 5.1 CAGED (24 meses)
1. **Download** de MOV, FOR e EXC de 202409 a 202608 do FTP (`src/download.py`), em `data/raw/` (fora do Git).
2. **Extração** (`py7zr`; o 7-Zip serve de alternativa) e leitura com **Polars** (`;`, decimal `,`, encoding a confirmar).
3. **Filtro** `uf == 42` logo na leitura, para não carregar o Brasil inteiro na memória.
4. **Consolidação MOV + FOR − EXC:** registros do EXC entram com o **sinal invertido** em `saldomovimentação` e são somados de forma agregada (não há ID de pessoa).
5. **Limpeza:**
   - remover colunas de índice (`Unnamed: 0`, `Unnamed: 0.1`) se aparecerem;
   - `idade` → inteiro; descartar idade < 14 ou > 80 nas análises de perfil;
   - `salário` (já mensal) → float; **para estatísticas salariais**, usar só `salário` > 0,3 × salário mínimo do mês e < R$ 100 mil, e excluir intermitentes (`categoria` 111) e `horascontratuais` = 0;
   - `valorsaláriofixo` **não** é usado (vem na unidade de pagamento: hora, dia…);
   - deflacionar salários pelo **INPC** para preços de ago/2026.
6. **Validação** (célula própria no notebook, com tabela de resultado):
   - bloco recente vs. base fornecida: contagens por mês × município (diferença esperada ≈ 0);
   - 24 meses vs. **Tabela 8.1** (por município) e **7.1** (SC): admissões, desligamentos e saldo. *Pré-teste com a base fornecida: diferença de **+0,05%** nas admissões e **+0,03%** nos desligamentos.*
7. **Saída:** `data/interim/caged_sc_24m.parquet` (fora do Git, grande).

### 5.2 RAIS (2024 e 2025)
1. Download de `RAIS_VINC_PUB_SUL.7z` (2024 e 2025) e filtro `Município` em SC (código de 6 dígitos).
2. **Filtrar vínculos CLT** (`Tipo Vínculo`), para ficar comparável ao CAGED (a RAIS inclui estatutários).
3. **Estoque em 31/12** (`Vínculo Ativo 31/12 = 1`) por município × subclasse CNAE × CBO, com escolaridade e remuneração de dezembro.
4. **Tempo de emprego** dos vínculos desligados no ano → % de desligamentos com menos de 12 meses de casa.
5. **Estoque mensal estimado** (método do próprio MTE): âncora em 31/12/2024 e 31/12/2025, rolando para frente e para trás com os saldos mensais do CAGED.
6. **Validação:**
   - (estoque 2025 − estoque 2024) ≈ saldo do CAGED em 2025, por município × seção;
   - estoque estimado somando todos os setores ≈ estoque oficial da Tabela 8.1.
7. **Saída:** `data/interim/rais_sc_estoque_{2024,2025}.parquet`.

### 5.3 Dimensões
- `dim_municipio`: código 6/7 dígitos, nome, micro, meso, população 2022 e 2026, IDHM, PIB per capita, escolarização. A base fornecida tem um **rodapé com HTML** (filtrar só as linhas com código de 7 dígitos) e `-` como nulo (mortalidade).
- `dim_cnae`: subclasse → divisão → seção → V1/V2/V3 → setor C.
- `dim_cbo`: código → descrição → hierarquia oficial → macrofamília → nível (IA).
- `dim_escolaridade`, `dim_tipomov` (admissão/desligamento, voluntário, descontado).
- `geo_sc_municipios.geojson`.

### 5.4 Saídas para o dashboard (versionadas, poucos MB)
Parquets agregados em `data/processed/`. O dashboard **nunca** lê microdados.

---

## 6. Indicadores

Todos são calculados para qualquer combinação **território × setor × macrofamília × bloco**, desde que respeitem o volume mínimo (§7.3).

| KPI | Fórmula | Leitura |
|---|---|---|
| **Saldo** | admissões − desligamentos | Criação líquida de vagas |
| **Saldo por 10 mil hab.** *(pedido no guia)* | saldo / população estimada 2026 × 10.000 | Compara cidades de tamanhos diferentes |
| **Variação relativa do emprego** | saldo / estoque no início do período | Crescimento proporcional à base empregada |
| **Aceleração** | variação relativa (recente) − variação relativa (anterior), em p.p. | "Expansão **acelerada**" |
| **Taxa de rotatividade descontada** *(oficial MTE)* | min(admissões, desligamentos descontados) / estoque médio | Giro "involuntário". *Desligamentos descontados* excluem a pedido (40), aposentadoria (50), morte (60) e transferência (80). *Estoque médio* = (estoque no início + estoque no fim) / 2. **Referência oficial out/25–set/26:** SC 33,6% · Brasil 34,2% · Transformação Brasil 27,6% |
| **Taxa de saída voluntária** | desligamentos a pedido (40) / total de desligamentos | Mercado aquecido: o trabalhador sai porque tem alternativa |
| **Desligamento precoce** *(RAIS)* | desligados com menos de 12 meses de casa / total de desligados | Problema de retenção ou de integração |
| **Gap salarial de reposição** | mediana do salário real de admissão / mediana do salário real de desligamento | < 1 = compressão (reposição mais barata); > 1 = empresa pagando mais para atrair |
| **Gap salarial de entrada** *(RAIS)* | mediana de admissão / mediana do estoque | Quanto o novato ganha em relação a quem já está empregado |
| **Gap de escolaridade** | % com médio completo ou mais (admitidos) − idem (estoque RAIS) | < 0 = empresas aceitando escolaridade menor (sinal de escassez) |

**Sintomas vs. causas** (organização usada no diagnóstico e no dashboard):
- **Sintomas de tensão (apagão):** rotatividade descontada, saída voluntária, desligamento precoce.
- **Dinamismo (expansão):** saldo por 10 mil hab., variação relativa, aceleração.
- **Causas candidatas:** gap salarial (renda), gap de escolaridade (qualificação), comparação SC × Brasil na mesma seção (estrutural vs. local).

---

## 7. Índice, classificação e robustez

### 7.1 Índice de Tensão (IT, o "índice de apagão")
- z-score de cada sintoma dentro do nível de agregação escolhido, com média ponderada. **Pesos iniciais iguais.**
- **Teste de sensibilidade:** recalcular com pesos alternativos e mostrar que o ranking dos 10 primeiros se mantém (ou mostrar o que muda).

### 7.2 Matriz de classificação
Eixo X = **Dinamismo** (variação relativa + aceleração, padronizados) · Eixo Y = **Tensão** (IT).

| | Tensão baixa | Tensão alta |
|---|---|---|
| **Dinamismo alto** | 🟢 Expansão saudável | 🟠 **Expansão sob pressão** (expansão acelerada que pressiona a infraestrutura e os salários) |
| **Dinamismo baixo** | ⚪ Estagnação / retração estável | 🔴 **Apagão / rotatividade crônica** |

Para cada célula crítica, um **diagnóstico de causa:**
- **Salarial:** gap de reposição < 0,95.
- **Qualificação:** gap de escolaridade negativo em macrofamília técnica ou de nível superior.
- **Estrutural:** a seção também retrai no Brasil (Tabela 6.1), ou seja, não é um problema só de SC.

### 7.3 Robustez estatística
- **Volume mínimo** por célula: ≥ 100 movimentações para taxas; ≥ 30 admissões **e** ≥ 30 desligamentos para medianas salariais. Abaixo disso a célula fica marcada como "amostra insuficiente".
- **Bootstrap** (1.000 reamostragens) para o intervalo de confiança de 95% da mediana salarial e do gap de reposição.
- Testes simples (por exemplo, Mann-Whitney) para a diferença salarial entre admitidos e desligados por escolaridade.

### 7.4 Análises complementares
- **Clusterização de municípios** (k-means; k escolhido por silhueta) sobre os indicadores padronizados, com visualização em PCA 2D e nomes descritivos para os clusters.
- **Correlações territoriais:** IT e dinamismo × PIB per capita, IDHM, escolarização e densidade (gráficos de dispersão; *correlação, não causalidade*).
- **SC × Brasil** por seção (variação relativa e rotatividade).
- **Série 2020–2026** do estoque de SC e das mesorregiões (contexto).

---

## 8. IA: macrofamílias de CBO

### 8.1 Processo
1. **Taxonomia fechada** (rascunho abaixo; aprovar antes de classificar).
2. **Rodada 1:** classificar os 2.207 CBOs presentes nos dados (código + descrição do dicionário), em lotes de ~100, saída em JSON/CSV: `cbo, descricao, macrofamilia, nivel_qualificacao, justificativa`.
3. **Rodada 2 independente** (sessão nova, ordem embaralhada) → **taxa de concordância** e lista de divergências.
4. **Arbitragem** das divergências (humano + IA) e **amostra manual** de ~50 CBOs revisada pela equipe.
5. **Checagem de coerência** com a hierarquia oficial (por exemplo, grande grupo 2 = profissionais das ciências, que deve cair em nível superior).
6. Versionar `prompts/classificacao_cbo.md` e `data/processed/cbo_macrofamilia.csv`. O notebook documenta o processo e reporta a concordância.

### 8.2 Taxonomia e regras (implementadas em `src/cbo_ia.py` e `src/mapeamentos.py`)
O prompt envia, por código: código, descrição (aba `cbo2002ocupação` do dicionário), `nivel_cbo` e família sugerida pelo prefixo. Saída: `data_processed/cbo_macrofamilias.csv` (`cbo2002ocupação, descricao, macrofamilia, nivel_qualificacao, lideranca, justificativa`). A rodada 2 repete a classificação com a ordem embaralhada (seed fixa), loga a concordância de família e nível e grava `data_processed/cbo_divergencias.csv`.

**A. Ofício, não setor.** A macrofamília é o ofício da ocupação, nunca o setor do empregador: faxineira em fábrica têxtil → Serviços de apoio; costureira → Têxtil em qualquer setor.

**B. Conjunto fechado (11 + `Não classificado`, R5.2).** Desempate pelo prefixo da CBO (o mais longo vence); a IA só foge da família sugerida com justificativa — sem ela, a família volta para a sugerida.

| # | Macrofamília | Prefixos CBO | Exemplos |
|---|---|---|---|
| 1 | Operação de linha e processo | 781, 784, 74, 81, 82, 83, 86 | 784205 Alimentador de linha, 784105 Embalador a mão |
| 2 | Metalmecânica e eletroeletrônica | 72, 73 | 724315 Soldador, 721215 Operador de máquinas-ferramenta |
| 3 | Construção civil e extração | 71 | 717020 Servente de obras, 715210 Pedreiro |
| 4 | Têxtil, confecção, couro e calçados | 76 | 763215 Costureiro, 763125 Ajudante de confecção |
| 5 | Alimentos e bebidas | 84 | 848520 Magarefe, 841505 Laticínios |
| 6 | Madeira, móveis, cerâmica e vidro | 75, 77 | 771105 Marceneiro, 752305 Ceramista |
| 7 | Manutenção e reparação | 91, 95, 99 | 911305 Mecânico de manutenção, 951105 Eletricista de manutenção |
| 8 | Logística e transporte | 782, 783, 414, 342 | 414105 Almoxarife, 782510 Motorista de caminhão |
| 9 | Engenharia, técnicos industriais e TI | 20, 21, 30, 31, 39, 317 | 391205 Inspetor de qualidade, 317110 Programador |
| 10 | Administrativo e comercial | 4 (exceto 414), 25, 35, 52 | 411010 Assistente administrativo, 521110 Vendedor |
| 11 | Serviços de apoio e outros | 51, saúde (22, 322), educação (23, 33), 6, 0 | 514320 Faxineiro, 517330 Vigilante |

Grande grupo 1 (dirigentes) não tem sugestão: vai para a família da área dirigida (142105 Gerente administrativo → Administrativo e comercial).

**C. Nível de qualificação** — 4 valores ordinais: Básico < Qualificado < Técnico < Superior. O `nivel_cbo` vem do 1º dígito (1 e 2 → Superior; 3 → Técnico; 4–9 e 0 → Qualificado); a IA confirma ou ajusta, com justificativa obrigatória ao divergir (sem ela, vale o `nivel_cbo`). Caso típico: rebaixar ocupações elementares para Básico.

**D. Liderança é flag, não nível.** `lideranca = True` se o 1º dígito for 1 ou a descrição começar com Supervisor, Mestre, Encarregado, Chefe, Gerente ou Diretor (calculada no código, não pela IA). O líder fica com a família e o nível do ofício que lidera (410105 Supervisor administrativo → Administrativo, Qualificado; 710205 Mestre de construção civil → Construção).

---

## 9. Recomendações

Cada recomendação nasce de uma **regra** que liga o diagnóstico (§7) a uma **alavanca da empresa**, sempre aplicada a **macrofamília × região**:

| Gatilho | Alavanca recomendada |
|---|---|
| Gap de reposição < 0,95 **e** saída voluntária alta | Revisar a faixa salarial de entrada e a política de reajuste; usar como referência a mediana regional da macrofamília |
| Desligamento precoce alto | Integração e acompanhamento nos primeiros 90 dias; revisão do processo seletivo |
| Gap de escolaridade negativo em macrofamília técnica | Formação interna / academia corporativa; parcerias de qualificação com escolas técnicas e universidades |
| Expansão sob pressão em uma região **e** retração na mesma macrofamília em região vizinha | Recrutamento entre regiões e programas de mobilidade (auxílio-moradia, transporte) |
| Operacional básico + rotatividade alta + reposição difícil | Automação e redesenho de postos de trabalho |
| Retração estrutural (SC e Brasil) | Requalificação e realocação interna para macrofamílias em expansão |

- **Fichas regionais:** 1 por mesorregião (diagnóstico + 3 recomendações priorizadas), textos redigidos com IA a partir dos números e revisados pela equipe.
- **Opcional:** estimativa do **custo da rotatividade** em R$ (premissa documentada, por exemplo custo de reposição = N salários), para falar a língua da banca.

---

## 10. Dashboard (Streamlit + Plotly)

**Filtros globais:** período (12m / 24m / comparação) · visão CNAE (V1/V2/V3 + setor C) · nível territorial (meso/micro/município) · macrofamília · nível de qualificação.

| Aba | Conteúdo | Pergunta que responde |
|---|---|---|
| **1. Panorama** | Cartões de KPI (saldo, variação relativa, rotatividade SC × Brasil, saída voluntária, gap de reposição) · mapa coroplético com métrica selecionável · série 2020–2026 | *Onde está o problema?* |
| **2. Diagnóstico** | Matriz Dinamismo × Tensão (bolhas = região × setor, tamanho = estoque) · ranking de alertas · comparação entre blocos | *Quem precisa de atenção urgente?* |
| **3. Causa raiz** | Salários de admitidos × desligados × estoque por escolaridade e macrofamília (com intervalo de confiança) · gap de escolaridade · desligamento precoce · dispersões territoriais (PIB, IDHM) | *Por quê: salário, qualificação ou estrutura?* |
| **4. Ocupações (IA)** | Treemap macrofamília × nível · tabela CBO → macrofamília · metodologia e concordância da IA | *Que tipo de profissional falta?* |
| **5. Recomendações** | Ficha por mesorregião · tabela de recomendações filtrável | *O que fazer?* |

- **Modo narrativa:** botão "Apresentar", que percorre 4 telas espelhando o pitch.
- **Metodologia** em expansores (fontes, validações, limites).
- **Publicação:** Streamlit Community Cloud, com link no README e no slide final.
- **Desempenho:** só lê `data/processed/`; usa `st.cache_data`.

---

## 11. Pitch (3 minutos)

| Tempo | Conteúdo | Slide |
|---|---|---|
| 0:00–0:20 | Gancho: "SC quase não cria vagas na indústria, mas troca 1 em cada 3 trabalhadores por ano" *(confirmar números)* | 1 |
| 0:20–0:50 | Método: 24 meses, MOV+FOR−EXC, RAIS, IA nos CBOs, **validado contra o MTE** | 2 |
| 0:50–2:00 | 3 achados: **onde** (mapa) → **quem** (matriz) → **por quê** (renda e escolaridade) | 3–5 |
| 2:00–2:40 | Recomendações para as empresas, ligadas às macrofamílias | 6 |
| 2:40–3:00 | Limites + link do dashboard | 7 |

Ensaiar com cronômetro; preparar respostas para perguntas prováveis da banca (por que proxies de apagão, como validamos a IA, por que RAIS).

---

## 12. Estrutura do repositório

```
datathon/
├── PLANEJAMENTO.md
├── README.md                    # como reproduzir, metodologia, premissas, limites, link do dashboard
├── requirements.txt
├── docs/                        # material dos organizadores
├── data/
│   ├── raw/                     # (gitignored) downloads FTP/IBGE
│   ├── interim/                 # (gitignored) parquets SC detalhados
│   └── processed/               # (versionado) dimensões, agregados, cbo_macrofamilia.csv, geojson
├── notebooks/
│   ├── 01_caged_ingestao_validacao.ipynb
│   ├── 02_rais_estoques.ipynb
│   ├── 03_dimensoes_territorio_cnae.ipynb
│   ├── 04_ia_cbo_macrofamilias.ipynb
│   ├── 05_indicadores_diagnostico.ipynb
│   └── 06_recomendacoes.ipynb
├── src/                         # funções reutilizadas pelos notebooks (download, caged, rais, dims, indicadores)
├── prompts/                     # prompts de IA versionados
├── app/                         # dashboard Streamlit
└── pitch/                       # slides e roteiro
```

**Stack:** Python 3.11+, Polars (volume) e Pandas (quando conveniente), py7zr, Plotly, Streamlit, scikit-learn, SciPy, openpyxl.

---

## 13. Frentes de trabalho

Cada frente pode ter um responsável. As dependências indicam o que bloqueia o quê.

### F1 — Base CAGED 24 meses *(sem dependências)*
- [ ] Script de download MOV/FOR/EXC 202409–202608
- [ ] Leitura com filtro SC + consolidação MOV+FOR−EXC
- [ ] Regras de limpeza (§5.1) e deflação pelo INPC
- [ ] Validação vs. base fornecida e vs. Tabelas 7.1/8.1
- [ ] `caged_sc_24m.parquet`

### F2 — RAIS *(sem dependências; depende de F1 só para o estoque mensal)*
- [ ] Download RAIS 2024/2025 Sul e filtro SC + CLT
- [ ] Estoques 31/12 por município × CNAE × CBO; perfil (escolaridade, remuneração)
- [ ] Tempo de emprego dos desligados
- [ ] Estoque mensal estimado + validações (§5.2)

### F3 — Dimensões e território *(sem dependências)*
- [ ] `dim_municipio` (IBGE + base fornecida tratada)
- [ ] `dim_cnae` (3 visões + setores C)
- [ ] GeoJSON SC
- [ ] Leitura das abas do xlsx oficial (7.1, 8.1, 6.1, 10, 11)

### F4 — IA nos CBOs *(sem dependências)*
- [ ] Aprovar a taxonomia (§8.2)
- [ ] Rodada 1 + Rodada 2 + concordância
- [ ] Arbitragem, amostra manual e checagem de hierarquia
- [ ] Prompt e CSV versionados + notebook 04

### F5 — Indicadores e diagnóstico *(depende de F1–F4)*
- [ ] KPIs (§6) em todos os recortes, com volume mínimo
- [ ] Índice de Tensão + sensibilidade
- [ ] Matriz e diagnóstico de causa
- [ ] Bootstrap e testes
- [ ] Clusterização, correlações, SC × Brasil, série 2020–2026
- [ ] Agregados para o dashboard em `data/processed/`

### F6 — Recomendações *(depende de F5)*
- [ ] Regras gatilho → alavanca
- [ ] Fichas por mesorregião
- [ ] (Opcional) custo da rotatividade

### F7 — Dashboard *(layout já pode começar; dados reais dependem de F5)*
- [ ] Esqueleto com as 5 abas e filtros globais (dados fictícios)
- [ ] Integração com `data/processed/`
- [ ] Modo narrativa + metodologia
- [ ] Deploy no Streamlit Cloud

### F8 — Documentação e pitch *(roteiro já pode começar)*
- [ ] README (reprodução, premissas, limites)
- [ ] Revisão final dos notebooks (markdown explicativo)
- [ ] Slides + roteiro
- [ ] Ensaio cronometrado + perguntas e respostas

---

## 14. Cronograma

| Quando | Meta |
|---|---|
| **10/11 (hoje)** | Repo e ambiente prontos · **iniciar downloads (F1/F2)** · F3 completa · taxonomia aprovada e Rodada 1 da IA |
| **11/11** | F1 e F2 processadas e validadas · F4 concluída · KPIs básicos (F5) · esqueleto do dashboard · rascunho do roteiro |
| **12/11** | F5 avançada (índice, matriz, bootstrap, clusters) · F6 · dashboard completo e publicado · slides · **congelar o código às 22h** |
| **13/11 08:30–09:50** | Ensaio, ajustes finais, **envio do formulário de entrega** |
| **13/11 10:30–11:30** | Pitch |

---

## 15. Premissas e limites (vão para o README e para o pitch)

1. **O CAGED não mede vagas abertas.** O "apagão" é **inferido** por sinais de tensão (rotatividade, saída voluntária, desligamento precoce, gaps).
2. Cobre só o **emprego formal CLT**. Informalidade, autônomos e PJ ficam fora.
3. **O estoque industrial é estimado** (RAIS + saldos do CAGED). O erro acumulado de jan a ago/26 é medido contra o estoque oficial municipal.
4. Os salários são **declarados** pelo empregador. Usamos medianas, deflacionadas pelo INPC, sem intermitentes.
5. O desligamento precoce só existe para 2024 e 2025 (a RAIS é anual, e a RAIS 2026 ainda não existe).
6. Correlações com dados municipais **não implicam causalidade**.
7. A classificação dos CBOs por IA é uma interpretação. É mitigada pela taxonomia fechada, pela dupla rodada e pela revisão humana.
8. A população usada é a **estimativa IBGE 2026**. O IDHM é de 2010 (último disponível) e falta para 2 municípios criados depois.

---

## 16. Pendências

- [ ] Aprovar a taxonomia de macrofamílias (§8.2)
- [ ] Dividir as frentes (§13) entre os integrantes
- [ ] Confirmar com os organizadores: uso de dados públicos externos (RAIS, FTP, IBGE) liberado? Horário-limite do formulário de entrega?
- [x] Organizar `docs/`: pasta única `docs/docs_admissao/` (xlsx oficial + CSVs exportados dele)
