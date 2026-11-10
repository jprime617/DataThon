# Implementation Plan: Datathon CAGED SC — Pipeline e Dashboard

## Overview

Este plano converte o design em passos de implementação incrementais em **Python 3.11.9**, seguindo a ordem natural do pipeline: setup → mapeamentos de domínio → ingestão → limpeza → cruzamento relacional → métricas → enriquecimento de CBO via LLM → agregação → upload Azure → dashboard → notebook orquestrador → README/docs. Cada etapa produz um artefato consumido pela seguinte, sem código órfão: o notebook orquestrador (tarefa 11) amarra tudo ponta a ponta.

Testes são sub-tarefas junto da implementação que validam. Propriedades 1–28 do design viram testes property-based com **Hypothesis** (mín. 100 exemplos, tag de rastreabilidade obrigatória); o restante usa testes de exemplo/integração com **pytest**, mockando LLM e Azure. Sub-tarefas marcadas com `*` são opcionais para a entrega mínima.

## Tasks

- [x] 1. Configurar estrutura do projeto, dependências e tooling de testes
  - Criar a árvore de pastas: `src/`, `tests/`, `notebooks/`, `data_processed/`, `dashboard/`, `dashboard/geo/`
  - Adicionar `__init__.py` em `src/` e `tests/`
  - Criar `requirements.txt` com versões exatas fixadas (sem faixas): `pandas==3.0.6`, `plotly==7.1.0`, `pyarrow`, `streamlit`, `openpyxl`, `azure-storage-blob`, SDK do LLM escolhido, `hypothesis`, `pytest` — todas com versão exata resolvida no ambiente
  - Instalar as dependências novas no ambiente pyenv (pyarrow, streamlit, openpyxl, azure-storage-blob, SDK LLM, hypothesis, pytest)
  - Definir módulo utilitário de logging de progresso por etapa (mensagem única por etapa — base para R8.4)
  - Definir exceção `ErroDeValidacao` compartilhada em `src/`
  - Configurar `pytest` para descobrir `tests/` e `conftest.py` com `@settings(max_examples=100)` padrão
  - _Requirements: 8.2_

- [x] 2. Implementar tabelas de domínio do dicionário (`src/mapeamentos.py`)
  - [x] 2.1 Carregar o `Dicionario_de_dados.xlsx` via openpyxl e expor os dicionários de domínio
    - Ler as abas/tabelas do dicionário e construir `GRAU_INSTRUCAO`, `RACA_COR`, `SEXO`, `TIPO_MOVIMENTACAO`, `CATEGORIA`, `TAM_ESTAB_JAN`, `UNIDADE_SALARIO`, `SECAO_CNAE` como dicionários código → rótulo
    - Expor a constante `MACROFAMILIAS` (5–12 famílias, incluindo `Não classificado`) para uso em `cbo_ia.py`
    - _Requirements: 2.5_
  - [x] 2.2 Escrever testes de exemplo para o carregamento de domínios
    - Verificar que cada dicionário esperado foi carregado e não está vazio e que `MACROFAMILIAS` tem entre 5 e 12 itens incluindo `Não classificado`
    - _Requirements: 2.5_

- [x] 3. Implementar o Ingestor (`src/ingestao.py`)
  - [x] 3.1 Implementar leitura dos arquivos de origem
    - `ler_caged(caminho)`: sep `;`, decimal `,`, encoding utf-8, descartando `Unnamed: 0.1` e `Unnamed: 0`
    - `ler_municipios(caminho)`: sep `,`
    - Levantar erro identificando o arquivo quando ausente/inacessível/ilegível
    - _Requirements: 1.1, 1.2, 1.3, 1.10_
  - [x] 3.2 Implementar validações de schema
    - `validar_uf(df)`: aprova sse todas as linhas têm `uf == 42`; em falha levanta `ErroDeValidacao` com a contagem de divergentes
    - `validar_colunas(df)`: aprova sse todas as colunas obrigatórias presentes; em falha lista exatamente as ausentes
    - _Requirements: 1.4, 1.5, 1.6, 1.7_
  - [x] 3.3 Implementar orquestração e persistência Parquet
    - `executar_ingestao(...)`: lê, valida, registra contagem de linhas de cada arquivo, persiste `caged_bruto.parquet` só após todas as validações passarem; retorna `IngestResult` com `linhas_caged`/`linhas_municipios`
    - _Requirements: 1.8, 1.9_
  - [x] 3.4 Escrever testes de propriedade do Ingestor
    - **Property 1: Validação de UF detecta e conta divergentes** — Validates: Requirements 1.4, 1.5
    - **Property 2: Validação de colunas identifica exatamente as ausentes** — Validates: Requirements 1.6, 1.7
    - **Property 3: Contagem de linhas lida é exata** — Validates: Requirements 1.9
    - **Property 4: Round-trip de persistência Parquet** — Validates: Requirements 1.3, 1.8
  - [x] 3.5 Escrever testes de exemplo de leitura e erro de arquivo
    - Ler fixtures pequenos de CAGED/municípios; verificar erro identificável quando arquivo ausente/ilegível
    - _Requirements: 1.1, 1.2, 1.10_

- [x] 4. Implementar o Limpador (`src/limpeza.py`)
  - [x] 4.1 Implementar conversão monetária BR → float
    - `brl_para_float(valor)`: converte formato BR para float 2 casas; NaN se não conversível
    - `limpar_moeda(df, colunas)`: aplica a colunas monetárias e coleta (coluna, competência, qtde não convertida)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 4.2 Escrever testes de propriedade da conversão monetária
    - **Property 5: Round-trip de conversão monetária BR ↔ float** — Validates: Requirements 2.1, 2.3
    - **Property 6: Valores inválidos e `-` tornam-se ausentes com contagem correta** — Validates: Requirements 2.2, 2.4
  - [x] 4.3 Implementar decodificação de domínios
    - `decodificar_dominios(df, mapas)`: substitui código por rótulo; preserva código desconhecido e registra (coluna, código, contagem); célula vazia → NaN sem interromper
    - _Requirements: 2.5, 2.6, 2.7_
  - [x] 4.4 Escrever teste de propriedade da decodificação de domínios
    - **Property 7: Decodificação de domínios mapeia conhecidos e preserva desconhecidos** — Validates: Requirements 2.5, 2.6
  - [x] 4.5 Implementar filtro de competência e orquestração da limpeza
    - `filtrar_competencia(df, 202509, 202608)`: mantém intervalo inclusivo e retorna df + contagem de excluídos
    - `limpar(df_caged, df_municipios, mapas)`: orquestra moeda, domínios e filtro; converte indicadores BR dos municípios e `-` → NaN
    - _Requirements: 2.3, 2.4, 2.8, 2.9_
  - [x] 4.6 Escrever teste de propriedade do filtro de competência
    - **Property 8: Filtro de competência particiona corretamente pelo intervalo inclusivo** — Validates: Requirements 2.8, 2.9

- [x] 5. Implementar a Junta_Relacional (`src/enriquecimento.py`)
  - [x] 5.1 Implementar normalização das chaves municipais
    - `chave_municipal_caged(codigo)`: 6 dígitos numéricos ou None se malformado
    - `chave_municipal_ibge(codigo7)`: 6 primeiros dígitos do IBGE ou None se malformado
    - _Requirements: 3.1, 3.2, 3.6_
  - [x] 5.2 Escrever teste de propriedade da normalização de chave
    - **Property 9: Normalização da chave municipal produz 6 dígitos ou rejeita** — Validates: Requirements 3.1, 3.2
  - [x] 5.3 Implementar o left join com contagens e alerta de limiar
    - `juntar(df_caged, df_municipios)`: left join preservando todo o CAGED válido; exclui chaves malformadas contando por base; registra nº sem correspondência e total; alerta com códigos não correspondidos se > 1%
    - _Requirements: 3.3, 3.4, 3.5, 3.6_
  - [x] 5.4 Escrever testes de propriedade do join
    - **Property 10: Left join preserva todo o CAGED válido** — Validates: Requirements 3.3
    - **Property 11: Contagem de não correspondência e alerta de limiar são corretos** — Validates: Requirements 3.4, 3.5
    - **Property 12: Registros com chave malformada são excluídos e contados por base** — Validates: Requirements 3.6

- [x] 6. Checkpoint — Garantir que todos os testes passam
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implementar o Calculador_de_Metricas (`src/metricas.py`)
  - [x] 7.1 Implementar Saldo_Liquido e Saldo_por_10k
    - `saldo_liquido(df, por)`: soma de `saldomovimentação` por recorte; 0 para recorte vazio
    - `saldo_por_10k(saldo_df, municipios)`: `(saldo/pop)*10_000` se pop > 0, senão NaN
    - _Requirements: 4.1, 4.2, 4.3, 4.10_
  - [x] 7.2 Escrever testes de propriedade de saldo
    - **Property 13: Saldo_Liquido é o balanço de admissões e desligamentos** — Validates: Requirements 4.1, 4.10
    - **Property 14: Saldo_por_10k segue a fórmula ou é ausente** — Validates: Requirements 4.2, 4.3
  - [x] 7.3 Implementar Turnover
    - `turnover(df, por)`: `min(adm, desl)/tamestabjan` limitado a [0,1]; NaN se estoque 0/ausente
    - _Requirements: 4.4, 4.5_
  - [x] 7.4 Escrever teste de propriedade do Turnover
    - **Property 15: Turnover está sempre em [0, 1] ou é ausente** — Validates: Requirements 4.4, 4.5
  - [x] 7.5 Implementar salário médio e distribuição de escolaridade
    - `salario_medio_por_movimentacao(df)`: média de `salário` por movimentação e Secao_Industrial ignorando NaN
    - `distribuicao_escolaridade(df)`: contagem/proporção de `graudeinstrução` entre admitidos e desligados por Secao_Industrial
    - _Requirements: 4.6, 4.7_
  - [x] 7.6 Escrever testes de propriedade de salário e escolaridade
    - **Property 16: Salário médio ignora ausentes e fica entre os extremos** — Validates: Requirements 4.6
    - **Property 17: Distribuição de escolaridade soma ao total** — Validates: Requirements 4.7
  - [x] 7.7 Implementar Indice_de_Aquecimento
    - `indice_aquecimento(saldo_mensal_df)`: `Saldo_por_10k + variacao_mensal`; variação 0 no primeiro mês da série
    - _Requirements: 4.8, 4.9_
  - [x] 7.8 Escrever teste de propriedade do Indice_de_Aquecimento
    - **Property 18: Indice_de_Aquecimento é a soma de nível e variação mensal** — Validates: Requirements 4.8, 4.9

- [x] 8. Implementar o Classificador_de_CBO (`src/cbo_ia.py`)
  - [x] 8.1 Implementar extração de CBOs e loteamento
    - `extrair_cbos(df)`: CBOs distintos descartando nulos/vazios
    - Função de loteamento: lotes de ≤100, disjuntos, concatenação = lista original
    - _Requirements: 5.1, 5.3_
  - [x] 8.2 Escrever testes de propriedade de extração e loteamento
    - **Property 19: Extração de CBOs retorna distintos não vazios** — Validates: Requirements 5.1
    - **Property 20: Loteamento respeita o limite de 100 e preserva o conjunto** — Validates: Requirements 5.3
  - [x] 8.3 Implementar montagem de prompt, chamada ao LLM e validação de resposta
    - `montar_prompt(lote)` e `classificar_lote(lote, client)`: retry ≤3, timeout 60s; macrofamília fora do conjunto ou ausente → `Não classificado`; esgotadas as tentativas, lote inteiro → `Não classificado` + log de falha
    - Ler credencial `LLM_API_KEY` de env var; interromper antes de chamar a API se ausente/vazia (guarda de credencial)
    - _Requirements: 5.2, 5.6, 5.7, 5.9, 8.5, 8.6_
  - [x] 8.4 Escrever testes de exemplo do fluxo de retry e guarda de credencial (LLM mockado)
    - Verificar retry até 3x e fallback `Não classificado` em timeout/falha; verificar interrupção quando credencial ausente
    - _Requirements: 5.7, 8.6_
  - [x] 8.5 Implementar consolidação do mapeamento, persistência e merge
    - `classificar_cbos(df, client)`: consolida 1 linha por CBO, persiste `cbo_macrofamilias.csv` + prompt usado, faz merge na base e conta CBOs sem correspondência
    - _Requirements: 5.4, 5.5, 5.8_
  - [x] 8.6 Escrever testes de propriedade do mapeamento e merge (LLM mockado)
    - **Property 21: Mapeamento CBO é único e dentro do conjunto, com fallback** — Validates: Requirements 5.2, 5.4, 5.6
    - **Property 22: Contagem de CBOs sem correspondência no merge é exata** — Validates: Requirements 5.5
  - [x] 8.7 Escrever teste de exemplo de persistência do prompt
    - Verificar que o prompt utilizado é gravado junto ao `cbo_macrofamilias.csv`
    - _Requirements: 5.8_

- [x] 9. Checkpoint — Garantir que todos os testes passam
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implementar o Agregador (`src/agregador.py`)
  - [x] 10.1 Implementar a agregação por recorte com indicadores municipais
    - `agregar(df_metricas, municipios)`: uma linha por (região, Secao_Industrial, Macrofamilia_CBO, mês); omite combinações sem registros; anexa população 2026/IDHM 2010/PIB 2023 (NaN quando ausente); arredonda métricas a 2 casas
    - _Requirements: 6.1, 6.2, 6.5, 6.6, 6.7_
  - [x] 10.2 Escrever testes de propriedade da agregação
    - **Property 23: Integridade do agregado (unicidade e origem)** — Validates: Requirements 6.1, 6.2
    - **Property 25: Métricas do agregado têm no máximo 2 casas decimais** — Validates: Requirements 6.5
    - **Property 26: Indicadores municipais anexados correspondem à base** — Validates: Requirements 6.6, 6.7
  - [x] 10.3 Implementar exportação com tratamento de falha
    - `exportar(df_agregado, destino)`: exporta Parquet/CSV; em falha registra erro com destino e não grava arquivo parcial
    - _Requirements: 6.3, 6.4_
  - [x] 10.4 Escrever teste de propriedade e de exemplo da exportação
    - **Property 24: Round-trip de exportação do agregado** — Validates: Requirements 6.3
    - Teste de exemplo: falha de exportação registra erro com destino e não deixa arquivo parcial — _Requirements: 6.4_

- [x] 11. Implementar o upload para Azure Blob Storage (`src/azure_upload.py`)
  - [x] 11.1 Implementar upload das tabelas agregadas com guarda de credencial
    - `upload_tabelas(caminho_local, container)`: lê credencial Azure de env var; interrompe sem enviar se ausente/inválida (sem dados parciais); faz upload das tabelas agregadas
    - _Requirements: 8.5, 8.7, 9.1, 9.3_
  - [x] 11.2 Escrever testes de exemplo/integração do upload (Azure mockado)
    - Verificar interrupção sem envio quando credencial ausente/inválida e upload bem-sucedido com mock
    - _Requirements: 9.1, 9.3, 8.7_

- [x] 12. Implementar o Dashboard Streamlit (`dashboard/app.py`)
  - [x] 12.1 Implementar carregamento de dados com fallback local
    - `carregar_dados()`: lê do Blob_Storage; fallback para cópia local em `data_processed/`; se ambos indisponíveis, sinaliza indisponibilidade e não renderiza KPIs/gráficos
    - _Requirements: 7.7, 7.8, 9.2, 9.6_
  - [x] 12.2 Escrever testes de exemplo do carregamento e fallback (Blob mockado)
    - Verificar leitura do Blob, fallback local e estado de indisponibilidade
    - _Requirements: 7.7, 7.8, 9.2, 9.6_
  - [x] 12.3 Implementar filtros e KPIs
    - `aplicar_filtros(df, periodo, regiao, secao, macrofamilia)` e `render_kpis(df)`: ≥3 KPIs com rótulo e valor; filtro vazio → KPIs em zero
    - _Requirements: 7.1, 7.5, 7.6_
  - [x] 12.4 Escrever teste de propriedade do filtro e exemplo dos KPIs
    - **Property 28: Filtro do dashboard é correto e completo** — Validates: Requirements 7.5
    - Teste de exemplo: ≥3 KPIs renderizados; filtro sem registros → KPIs em zero — _Requirements: 7.1, 7.6_
  - [x] 12.5 Implementar mapa coroplético, ranking de setores e dispersão renda × escolaridade
    - `render_mapa(df, geojson)`: coroplético de SC por `saldo_por_10k`, escala divergente com legenda mín/máx, usando `dashboard/geo/sc_municipios.geojson`
    - `render_ranking(df)`: barras de Secao_Industrial ordenadas decrescentemente por `saldo_liquido`, exibindo saldo e turnover
    - `render_dispersao(df)`: `salario_medio_admissao` × `graudeinstrução` segmentado por seção/macrofamília
    - _Requirements: 7.2, 7.3, 7.4_
  - [x] 12.6 Escrever teste de propriedade do ranking e exemplo das visualizações
    - **Property 27: Ranking de setores é ordenado de forma não crescente** — Validates: Requirements 7.3
    - Teste de exemplo: mapa, ranking e dispersão renderizam com dados mínimos — _Requirements: 7.2, 7.4_
  - [x] 12.7 Adicionar gráfico bônus de série temporal do saldo mensal
    - Linha do saldo mensal por recorte (bônus, não exigido pela entrega mínima)
    - _Requirements: 7.4_

- [x] 13. Implementar o notebook orquestrador (`notebooks/01_pipeline.ipynb`)
  - [x] 13.1 Encadear o pipeline ponta a ponta com logging por etapa
    - Executar em sequência ingestão → limpeza → junção → métricas → CBO/LLM → agregação → upload, sem intervenção manual, produzindo os artefatos consumidos pelo dashboard; registrar mensagem de progresso única por etapa
    - _Requirements: 8.1, 8.4_
  - [x] 13.2 Escrever teste de integração ponta a ponta sobre fixture pequeno (LLM e Azure mockados)
    - Executar o pipeline sobre um fixture reduzido e verificar os artefatos de saída
    - _Requirements: 8.1_

- [x] 14. Escrever README e documentação de premissas
  - [x] 14.1 Escrever `README.md` e documentar premissas
    - README com pré-requisitos de ambiente, comandos de instalação de dependências, comandos de execução do pipeline e comandos para iniciar o dashboard
    - Documentar premissas: (a) exclusões já aplicadas na origem (`indicadordeexclusão`/`competênciaexc` ausentes); (b) IDHM referente a 2010 e desatualizado; (c) agrupamento de CBOs roda fora do Azure (sem Azure OpenAI); SKUs elegíveis para conta de estudante
    - Confirmar que credenciais são lidas só de env vars e que não há segredos versionados
    - _Requirements: 2.10, 8.3, 8.5, 8.8, 9.4, 9.5_
  - [x] 14.2 Escrever testes de smoke/checagens documentais
    - Verificar `requirements.txt` com versões exatas fixadas (sem faixas), README com as seções exigidas, premissas documentadas presentes
    - _Requirements: 8.2, 8.3, 8.8, 9.5_

- [x] 15. Checkpoint final — Garantir que todos os testes passam
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tarefas marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido (testes e o gráfico bônus de série temporal).
- Cada tarefa referencia cláusulas específicas de requisitos (R1–R9) para rastreabilidade.
- Checkpoints garantem validação incremental em pontos naturais do pipeline.
- Testes de propriedade (Hypothesis, ≥100 exemplos) validam as propriedades universais 1–28; testes de exemplo/integração cobrem leituras concretas, retry do LLM, upload Azure, renderização e documentação.
- Cada teste de propriedade deve incluir a tag de rastreabilidade: `# Feature: datathon-caged-sc-pipeline, Property {número}: {texto}`.
- LLM e Azure são sempre mockados nos testes para isolar lógica e evitar custo/rede.

## Correções pós-auditoria

Auditoria do repositório após a conclusão das tarefas 1–15 encontrou que a suíte
passava (138/138) enquanto o pipeline real produzia números errados: os fixtures
descreviam o formato que se *acreditava* que os arquivos tinham, não o que eles
têm. As correções abaixo foram aplicadas, cada uma com teste que falha se
regredir.

- [x] **C1 — `streamlit run` falhava no import.** O Streamlit coloca só a pasta do
  script no `sys.path`; `dashboard/app.py` passa a resolver a raiz do projeto a
  partir de `__file__` antes de importar `src.*`.
- [x] **C2 — `main()` era um stub.** Passa a montar a barra lateral de filtros e a
  chamar os cinco `render_*` na ordem da narrativa, com guard `__main__`.
- [x] **C3 — Turnover ausente em 100% dos recortes.** `tamestabjan` é *código de
  faixa*, não contagem de vínculos. O Limpador passa a derivar `estoque_base`
  (ponto médio da faixa) **antes** da decodificação de domínios; `metricas.turnover`
  usa essa coluna. Glossary e R4.4 corrigidos em `requirements.md`.
- [x] **C4 — IDHM e PIB corrompidos por 10²–10³.** `Municipios_SC_limpo.csv` usa
  ponto decimal, não formato brasileiro: `limpar_indicadores_municipios` passa a
  usar `pandas.to_numeric`. R2.3 corrigido em `requirements.md`.
- [x] **C5 — 2.206 de 2.206 CBOs como `Não classificado`.** O modelo configurado
  estava aposentado e toda chamada falhava, caindo no fallback silenciosamente.
  Adaptadores concretos (`ClienteGemini`, `ClienteClaude`) movidos para `src/`,
  seleção por `LLM_PROVIDER`, falha permanente (HTTP 400/401/403/404) passa a
  **interromper** em vez de virar fallback, e log de ALERTA acima de 50% de
  fallback.
- [x] **A1 — Mapa sem malha.** `scripts/baixar_malha_sc.py` baixa os 295
  municípios do IBGE e reescreve a chave das *features* para 6 dígitos.
- [x] **A2 — Dispersão renda × escolaridade sem fonte.** O Agregador passa a
  emitir `salario_medio_admissao`, `salario_medio_desligamento` e
  `escolaridade_media`; `metricas.salario_medio_por_movimentacao` ganhou recorte
  parametrizável e `escolaridade_media_por_movimentacao` foi acrescentada. R6.5 e
  R7.4 atualizados.
- [x] **A3 — Container do Blob divergente.** Pipeline e dashboard passam a ler o
  nome da mesma variável `AZURE_BLOB_CONTAINER`.
- [x] **A4 — Notebook nunca executado.** Executado ponta a ponta sobre os dados
  reais, com célula final de checagem de sanidade.
- [x] **M1 — Fixture mascarava C3 e C4.** Fixture alinhado aos formatos reais e
  `tests/test_contrato_dados_reais.py` acrescentado: lê o cabeçalho dos arquivos
  em `Dados/` e afirma as premissas de formato.
- [x] **M3 — Denominador do alerta de 1%.** `JoinResult` passa a expor
  `total_caged` (lido) e `total_caged_valido`; R3.4 atualizado.
- [x] **M4 — Código morto em `decodificar_dominios`** removido.
- [x] **M5 — `regiao` duplicava `municipio`.** Passa a ser a mesorregião do IBGE
  (`MESORREGIAO_POR_MUNICIPIO`), tornando o filtro de região do dashboard uma
  escolha entre 6 regiões em vez de 295 códigos. Property 23 ajustada: a chave do
  recorte é o município, e a região é atributo dele.
- [x] **M6 — Sem git e sem `.gitignore`.** Repositório inicializado com
  `.gitignore` cobrindo `.venv/`, o CSV bruto, o Parquet intermediário e `.env`.
- [x] **Deploy no Azure.** `startup.sh`, `.env.example` e seção de implantação no
  README; `src/mapeamentos.py` passou a carregar o dicionário de forma tardia
  (PEP 562) para que o App Service não precise embarcar `Dados/` nem `openpyxl`.


## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.5"] },
    { "id": 3, "tasks": ["3.3", "4.1", "5.1"] },
    { "id": 4, "tasks": ["3.4", "4.2", "4.3", "5.2"] },
    { "id": 5, "tasks": ["4.4", "4.5", "5.3", "8.1"] },
    { "id": 6, "tasks": ["4.6", "5.4", "7.1", "8.2", "8.3"] },
    { "id": 7, "tasks": ["7.2", "7.3", "7.5", "7.7", "8.4", "8.5"] },
    { "id": 8, "tasks": ["7.4", "7.6", "7.8", "8.6", "8.7", "10.1"] },
    { "id": 9, "tasks": ["10.2", "10.3", "11.1"] },
    { "id": 10, "tasks": ["10.4", "11.2", "12.1"] },
    { "id": 11, "tasks": ["12.2", "12.3", "12.5"] },
    { "id": 12, "tasks": ["12.4", "12.6", "12.7", "13.1"] },
    { "id": 13, "tasks": ["13.2", "14.1"] },
    { "id": 14, "tasks": ["14.2"] }
  ]
}
```
