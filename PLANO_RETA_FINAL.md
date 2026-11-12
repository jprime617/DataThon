# Plano da reta final: marcos e ciclos (12/11/2026)

**Prazo (PLANEJAMENTO §14):** código congelado hoje às **22h**, entrega em 13/11 às 08:30 e pitch às 10:30.
**Ponto de partida:** `dashboard-v2` em `717ce13`, com 232 testes verdes (`pytest -q`, cerca de 2,5 min).
**Base deste plano:** o parecer "Realinhamento do Raio-X SC", conferido contra o código. Os três problemas de método foram confirmados e os números batem.
As estimativas de tempo são chutes, servem para decidir o corte das 18h.

### Progresso (atualize a cada ciclo; é o primeiro lugar que a IA de cada um deve ler)

| Marco | Situação | Onde está | Último ciclo feito |
|---|---|---|---|
| M0 | C1 e C2 feitos; falta o C0 (organizadores) | `dashboard-v2` | M0.C2 |
| M1 | **concluído e mergeado** | `dashboard-v2` | M1.C5 |
| M2 | prompts prontos; código não iniciado | — | — |
| M3 | **mergeado** (C1–C4, C6, C7); **C5 (mapa) suspenso** | `dashboard-v2` | M3.C7 |
| M4 · M5 · M6 | bloqueados pelo M0.C0 | — | — |
| M7 | não iniciado | — | — |

Commits locais só sobem com autorização do João: confira `git log origin/dashboard-v2..` antes de supor que algo foi publicado.

---

## Como trabalhar (vale para todos)

1. **Um ciclo = um commit** com a mensagem `Mx.Cy: o que mudou`, e com os testes do que foi mexido verdes. Antes de mergear um marco, rode o `pytest -q` completo.
2. **Mudou comportamento?** Atualize o teste e o critério do `.kiro/specs/datathon-caged-sc-pipeline/requirements.md` no **mesmo** commit. Nunca deixe teste defendendo o desenho antigo.
3. **No mesmo commit**, marque o `[x]` do ciclo neste arquivo e atualize a linha **Estado** do marco.
4. **Vai parar no meio?** Faça commit com `WIP Mx.Cy: …`, escreva no **Estado** do marco onde parou, qual é o próximo passo e o cuidado que o próximo precisa ter, e dê `git push`.
5. **Um marco = uma branch** criada a partir de `dashboard-v2` (o nome está no cabeçalho do marco). O merge em `dashboard-v2` só acontece quando o "Pronto quando" do marco estiver cumprido.
6. **Só o dono do painel mexe em `dashboard/`.** Os ciclos marcados com **[painel]** são dele, mesmo dentro de um marco de dados. Isso evita conflito.
7. **Dados grandes nunca vão para o Git:** `data/raw/` e `data/interim/` ficam fora. Artefatos pequenos vão em `data_processed/`.
8. **Sem dependência nova.** Para descompactar, use o `7z` de linha de comando. Para ler, use pandas com `chunksize`.

### Como continuar de onde alguém parou

```bash
git fetch && git switch <branch do marco>
```

```bash
git log --oneline dashboard-v2..HEAD
```

Depois leia o **Estado** do marco aqui e rode `pytest -q`. Para fazer pelo Claude, cole isto:

```text
Leia PLANO_RETA_FINAL.md, seção "Como trabalhar". Continue o marco <Mx> a partir do primeiro ciclo não marcado (veja o Estado do marco e o último commit). Siga as regras: um ciclo por commit, teste e requirements.md junto, marque o checkbox e atualize o Estado. Não faça merge, push nem deploy sem me perguntar.
```

---

## Mapa dos marcos

| Marco | O quê | Depende de | Dados externos? | Branch |
|---|---|---|---|---|
| **M0** | Preparação e liberação | — | — | `dashboard-v2` |
| **M1** | Corrigir os 3 problemas de método | M0 | não | `m1-metodo` |
| **M2** | IA dos CBOs com a IA paga | M0 | não | `m2-ia` |
| **M3** | Painel simplificado para leigos | **M1 mergeado** | não | `m3-painel` |
| **M4** | RAIS 2025: estoque, rotatividade oficial, desligamento precoce | M0 (dados) · M1 (painel) | **sim** | `m4-rais` |
| **M5** | CAGED 24 meses (MOV + FOR − EXC) e INPC | M0 | **sim** | `m5-caged24` |
| **M6** | Validação contra as tabelas oficiais | M5 (ou 12 meses, se M5 não fechar) | **sim** | `m6-validacao` |
| **M7** | Integração, deploy e congelamento | tudo que foi mergeado | — | `dashboard-v2` |

### Agenda sugerida (5 pessoas)

| Pessoa | 12h–14h | 14h–18h | 18h | 19h–22h |
|---|---|---|---|---|
| 1 · **dono do painel** | M1 | M3 → ciclos [painel] de M4 e M5 | **corte** | M7 |
| 2 · dados RAIS | M4.C1–C2 | M4.C3–C4 | corte | apoio no M7 |
| 3 · dados CAGED | M5.C1–C3 | M5.C4–C6 | corte | apoio no M7 |
| 4 · IA | H1 (23 prompts) | M2.C1–C4 | corte | revisar números |
| 5 · validação e pitch | M0.C0 · baixar o xlsx · M6.C1 | M6.C2–C3 · slides | corte | ensaio do pitch |

**Corte das 18h:** o que não cumpriu o "Pronto quando" não entra. Vai para "Próximos passos" no pitch e no `PLANEJAMENTO.md`. Ciclos marcados **(mergeável sozinho)** podem entrar mesmo com o marco incompleto.

---

## M0 · Preparação

**Estado:** C1 feito (plano e `ia_cbo/` no Git, `/data/` ignorado). C2 feito (EXC com peso −1 no PLANEJAMENTO §5.1). Falta só o C0 (resposta dos organizadores) · Responsável: João

- [ ] **M0.C0 (humano), bloqueia M4, M5 e M6.** Confirmar com os organizadores se dados públicos externos (FTP do MTE, RAIS, IBGE) são permitidos (PLANEJAMENTO §16). Registre a resposta aqui. Se for não, M4, M5 e M6 saem do plano.
- [x] **M0.C1** Acrescentar `data/` ao `.gitignore`. Commitar este plano e a pasta `ia_cbo/`, e dar push em `dashboard-v2` para a equipe enxergar.
- [x] **M0.C2** `PLANEJAMENTO.md` §5.1, passo 4: trocar "EXC com sinal invertido" por "cada linha do EXC entra com **peso −1** e mantém o tipo". Inverter o sinal acerta o saldo, mas conta uma admissão excluída como desligamento.

---

## M1 · Corrigir os 3 problemas de método (sem dado novo)

**Branch:** `m1-metodo` · **Dono:** pessoa 1 · **Estimativa:** 1,5 a 2 h
**Estado:** concluído (C1–C5) e mergeado em `dashboard-v2` (merge `1fe52aa`). `pytest -q`: 227 verdes (os 7 a menos são os testes de turnover/aquecimento apagados). Notas: a regra de Automação virou "Básico ≥ 50% e saldo ≤ 0"; sem filtro, a sanfona não mostra delta; o `caged_agregado.parquet` atual ainda tem `turnover`/`indice_aquecimento` (o painel ignora), que somem na próxima reagregação (M7.C1).

O que muda, e por quê:
- **Giro:** hoje é `min(adm, desl) / max(adm, desl)`, que é função exata do saldo relativo (indústria: 0,9954 = (1−|s|)/(1+|s|)). Sai de tudo. A rotatividade oficial volta no M4.
- **Tensão:** hoje soma giro, saída voluntária e compressão salarial, e depois a compressão aparece também como "causa". Passa a usar **só sintomas**: por ora só a saída voluntária, e o M4 traz os outros dois.
- **Aceleração:** hoje compara set–fev com mar–ago, o que mede calendário (+4,3 p.p. na indústria). Sai. Volta calculada por blocos de 12 meses no M5.

- [x] **M1.C1 Tensão só com sintomas.**
  - Em `dashboard/comum.py`: `PESOS_TENSAO_PADRAO = {M_SAIDA_VOL: 1.0}`. Tirar `"compressao"` dos componentes e dos motivos.
  - A compressão continua só como causa (`causas()`, Salarial).
  - Em `diagnostico.py`, esconder o expander de sensibilidade enquanto houver um único componente; ele volta no M4.C6.
  - Testes: `test_dashboard_metricas.py`.
- [x] **M1.C2 Giro fora.**
  - Apagar `M_GIRO` de `comum.py`: definição, `KPIS_PADRAO`, grupos de indicadores, `METRICAS_INVERSAS` e as regras de recomendação que o usam.
  - Apagar também de `narrativa.py`, `figuras.py`, `paginas/` (panorama, diagnóstico, causa raiz, recomendações, apresentação, metodologia) e dos testes.
  - Conferir com `grep -rn "M_GIRO\|giro" dashboard tests`, que deve voltar vazio.
- [x] **M1.C3 Aceleração semestral fora.**
  - Tirar `M_ACEL` do Dinamismo (`PESOS_DINAMISMO_PADRAO = {M_SALDO_REL: 1.0}`), dos KPIs, do mapa e da sanfona.
  - **Apagar** `corte_semestral` e o cálculo semestral em `agregar_metricas`. O M5.C6 recria a aceleração por blocos.
- [x] **M1.C4 Colunas legadas do pipeline.**
  - Remover `turnover` (R4.4–R4.5) e `indice_aquecimento` (R4.8–R4.9) de `src/metricas.py`, `src/agregador.py`, do notebook e dos testes (`test_metricas_turnover.py` e `test_metricas_aquecimento.py`, além das menções em `test_agregador_propriedades.py` e `test_pipeline_integracao.py`).
  - No `requirements.md`, R4.4 e R6.5 passam a apontar para a rotatividade descontada (M4), com a observação "pendente de RAIS".
- [x] **M1.C5 Fechamento.**
  - Reescrever o texto da Metodologia sobre o índice: "Tensão = sintomas; causas ficam no diagnóstico".
  - `pytest -q` completo.
  - `streamlit run dashboard/app.py` e clicar por todas as páginas.

**Pronto quando:** nenhuma tela mostra giro ou aceleração semestral; a compressão aparece só como causa; a Metodologia descreve o índice novo; `pytest -q` está verde.

---

## M2 · IA dos CBOs com a IA paga (via chat, substitui o Gemini)

**Branch:** `m2-ia` · **Dono:** pessoa 4 · **Estimativa:** H1 de 1 a 1,5 h, código de cerca de 1 h
**Estado:** prompts prontos em `ia_cbo/prompts/` (23 lotes, 2.207 CBOs, ≤ 100 por lote)

- [ ] **H1 (humano)** Rodar os 23 prompts na IA paga e salvar em `ia_cbo/respostas/lote_NN.json`. O passo a passo, o formato e a conferência estão em `ia_cbo/COMO_USAR.md`.
- [ ] **M2.C1 `ClienteArquivo` em `src/cbo_ia.py`.**
  - Implementa `ClienteLLM`. No `__init__`, junta todos os `respostas/lote_*.json` com `_extrair_mapeamento`. `classificar()` devolve `json.dumps(dict_inteiro)`, porque `classificar_lote` já filtra os códigos do lote.
  - Se faltar a resposta de algum `prompts/lote_NN.txt`, levanta `ErroDeValidacao` listando os lotes faltantes.
  - Em `criar_cliente_llm`, adicionar `LLM_PROVIDER=arquivo`, sem exigir `LLM_API_KEY`. O nome do modelo vem de `LLM_MODELO_MANUAL`.
  - Teste novo: `tests/test_cbo_ia_arquivo.py` (junta dois arquivos; um lote faltante dá erro).
- [ ] **M2.C2 Concordância Gemini × IA paga.**
  - Copiar o `data_processed/cbo_macrofamilias.csv` atual para `cbo_macrofamilias_gemini.csv`.
  - Com o provedor `arquivo`, a rodada 2 compara com esse CSV, e não com a reexecução embaralhada (que daria 100% trivialmente). Usar `_registrar_concordancia`.
  - O `meta.json` registra o provedor, o modelo e a nota "classificação via chat; prompts e respostas em `ia_cbo/`".
- [ ] **M2.C3 Reclassificar e reagregar** (depois do H1).
  - Rodar as etapas 5 e 6 do notebook com `LLM_PROVIDER=arquivo`.
  - No `requirements.md`, R5.7, R5.9 e R8.6 passam a valer só para os provedores por API, e entra um critério novo para o modo arquivo. README ganha uma seção "classificação via chat".
- [ ] **M2.C4 Revisão humana** (parecer F4): revisar as 20 divergências de maior volume em `cbo_divergencias.csv`. Para corrigir, edite o `lote_NN.json`, com justificativa começando por "Revisão humana:", e rode o C3 de novo.
- [ ] **M2.C5 CBOs novos** (só se o M4 ou o M5 trouxer códigos sem classificação, acima de 1% do estoque ou das movimentações): gerar `lote_24+` com o mesmo script e voltar ao H1 só para eles.

**Pronto quando:** o `cbo_macrofamilias.csv` vem da IA paga, a concordância Gemini × IA paga aparece na página Ocupações e `pytest -q` está verde.

---

## M3 · Painel simplificado (anotações da equipe)

**Branch:** `m3-painel`, criada **depois** do merge do M1 · **Dono:** pessoa 1 · **Estimativa:** 3 a 4 h
**Estado:** C1–C4, C6 e C7 feitos em `m3-painel` (**mergeado** em `dashboard-v2`). **C5 (mapa) suspenso** a pedido do João: o R7.2 aparece se o usuário escolher "Saldo por 10 mil hab." + "Município", mas o mapa ainda abre em saída voluntária por microrregião. O R7.4 não existia e foi criado (dispersão salário médio de admissão × escolaridade ordinal média, em Por que acontece → Aprofundar). Menu renomeado (URLs iguais). `pytest -q`: 236 verdes. Pendente: só o C5, se o João liberar (fazer numa branch nova a partir de `dashboard-v2`).

- [x] **M3.C1 Diagnóstico em cartões.** A tabela de 9 colunas vira cartões de semáforo: "onde · situação · por quê, numa frase · 2 números".
- [x] **M3.C2 Matriz legível.** Só cor, sem os 4 símbolos. Eixos com palavras ("cresce pouco → cresce muito" / "segura a equipe → perde a equipe"), sem "z-score" na tela.
- [x] **M3.C3 Linguagem leiga.** "Gap 0,94" vira "paga 6% abaixo de quem saiu". No máximo 4 KPIs principais, e o resto em "Aprofundar". Menu sem jargão ("Por que acontece", "Que profissional falta").
- [x] **M3.C4 No máximo 2 gráficos por página.** As dispersões de PIB/IDHM saem de Causa raiz e vão para um expander.
- [ ] **M3.C5 Mapa (R7.2).** Abre em saldo por 10 mil hab., **por município**, com escala divergente e legenda de mínimo e máximo. A bolha mostra o volume de movimentações; no máximo duas camadas.
- [x] **M3.C6 Ranking de seções (R7.3).** Seções por saldo, ao lado da rotatividade descontada (se o M4 entrou) ou da saída voluntária (se não). Ajustar o texto do R7.3 de acordo.
- [x] **M3.C7 Tabela "requisito → onde aparece"** na Metodologia, de R1 a R9, para a banca. Conferir também o R7.4 (salário × nível ordinal médio de escolaridade).

**Pronto quando:** um leigo entende cada página sem explicação, R7.2, R7.3 e R7.4 estão visíveis e `pytest -q` está verde.

---

## M4 · RAIS 2025: estoque, rotatividade oficial e desligamento precoce

**Branch:** `m4-rais` · **Dono:** pessoa 2 (C1–C4) e pessoa 1 nos ciclos [painel] · **Estimativa:** 3 a 4 h · **Exige M0.C0**
**Estado:** não iniciado. O FTP respondeu em 12/11: `ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/2025/RAIS_VINC_PUB_SUL.7z` (705 MB).

**Ideia central:** **só a RAIS 2025.** O estoque em 31/12/2025 cai dentro da janela set/25–ago/26 e serve de aproximação do estoque médio. Assim saem a rotatividade descontada (PLANEJAMENTO §6), a variação relativa (saldo ÷ estoque), o desligamento precoce e o gap de escolaridade contra o estoque. A RAIS 2024 e o estoque mensal rolado ficam para depois.

- [ ] **M4.C1 Baixar e inspecionar** (mergeável sozinho).
  - Script que baixa para `data/raw/rais/2025/`, retomável (pula o que já existe), e extrai com `7z`.
  - Baixar também o layout da RAIS no FTP e anotar no Estado: nomes das colunas, separador, encoding e os códigos de `Tipo Vínculo` CLT e de `Vínculo Ativo 31/12`. **Conferir no layout, não de memória.**
- [ ] **M4.C2 `src/rais.py: ler_rais_sc()`.**
  - Leitura em `chunksize`, filtrando município de SC (6 dígitos começando com 42) e vínculos CLT. Manter só as colunas necessárias.
  - Grava `data/interim/rais_sc_2025.parquet`.
  - Um teste com um CSV sintético de 5 linhas.
- [ ] **M4.C3 `estoque_rais()` → `data_processed/rais_estoque.parquet`.**
  - Chaves iguais às do agregado, **sem `mes`**.
  - Colunas: `estoque_31dez`, `estoque_medio_ou_mais` (médio completo ou mais), `desligados_rais` e `desligados_precoce` (menos de 12 meses de casa).
  - Reaproveitar o mapeamento subclasse → seção/setor do `agregador.py` e o `aplicar_mapeamento` dos CBOs.
  - Registrar a % do estoque em CBOs sem macrofamília; se passar de 1%, acionar o M2.C5.
- [ ] **M4.C4 Desligamentos descontados no CAGED.**
  - Nova coluna aditiva `desligamentos_descontados` em `src/agregador.py` (`COLUNAS_ADITIVAS` e `preparar_base`): desligamentos menos os códigos 40, 50, 60 e 80 (PLANEJAMENTO §6).
  - Atualizar a checagem de schema e reagregar.
  - ⚠️ O M5.C3 mexe na mesma função. Quem mergear por último faz o rebase.
- [ ] **M4.C5 [painel] Carregar o estoque.**
  - `rais_estoque.parquet` entra em `carregar_artefatos` (local e Blob, com novo `NOME_BLOB_*`) e no schema.
  - Em `agregar_metricas`, o estoque é somado pelos mesmos `por` e anexado. **Nunca replicar o estoque nas linhas mensais.**
  - Métricas novas: `rotatividade_desc = min(adm, desl_desc) / estoque`, `variacao_rel = saldo / estoque` e `precoce = desligados_precoce / desligados_rais`.
- [ ] **M4.C6 [painel] Índice e KPIs.**
  - Tensão = rotatividade descontada + saída voluntária + precoce, com pesos iguais e o expander de sensibilidade de volta. Dinamismo = variação relativa.
  - KPI de rotatividade ao lado da referência oficial (SC 33,6%, Brasil 34,2%, Transformação Brasil 27,6%; PLANEJAMENTO §6).
  - **Checagem:** a rotatividade de SC com todas as seções tem que ficar perto de 33,6%. Se ficar longe, investigar antes de publicar.
- [ ] **M4.C7 (opcional)** Gap de escolaridade contra o estoque (no lugar de admitidos − desligados) e recomendação "desligamento precoce → integração nos primeiros 90 dias" (parecer F6).

**Pronto quando:** a rotatividade descontada aparece no Panorama ao lado da referência oficial, o índice tem os 3 sintomas, a Metodologia explica "estoque de 31/12/2025 como aproximação do estoque médio" e `pytest -q` está verde.

---

## M5 · CAGED 24 meses (MOV + FOR − EXC) e INPC

**Branch:** `m5-caged24` · **Dono:** pessoa 3 e pessoa 1 no [painel] · **Estimativa:** 4 a 5 h · **Exige M0.C0**
**Estado:** não iniciado. O FTP já tem até 202609, mas a janela continua **set/24–ago/26** (D1), para bater com a base fornecida.

- [ ] **M5.C1 `src/download.py`** (mergeável sozinho).
  - Baixa `NOVO CAGED/AAAA/AAAAMM/CAGED{MOV,FOR,EXC}AAAAMM.7z` de 202409 a 202608 (72 arquivos, cerca de 1,3 GB) para `data/raw/caged/`, de forma retomável.
  - **Deixe rodando em segundo plano** e siga para o C2.
- [ ] **M5.C2 INPC** (mergeável sozinho).
  - `src/inpc.py` busca o SIDRA (tabela 1736, variável 44) e grava `data_processed/inpc.csv`, versionado, para o pipeline rodar offline.
  - Em `src/limpeza.py`, deflacionar o `salário` para preços de ago/2026.
  - Teste: o fator de 202608 é 1.
- [ ] **M5.C3 Ler e consolidar.**
  - Extrair um arquivo por vez com `7z`, ler com `chunksize` (separador `;`, decimal `,`), filtrar `uf == 42` e apagar o `.txt`.
  - Coluna `peso`: +1 para MOV e FOR, **−1 para EXC**, mantendo o tipo. Admissões e desligamentos são a soma de `peso` por tipo, e o saldo é Σ `peso × saldomovimentação`.
  - Filtrar por `competênciamov` dentro da janela. Grava `data/interim/caged_sc_24m.parquet`.
- [ ] **M5.C4 Validar a leitura (portão).**
  - Bloco recente, **só o MOV**, contra `Dados/Novo_Caged_MOV_Limpo.csv`, por mês × município × (adm, desl). Grava `data_processed/validacao_base_fornecida.csv`.
  - **Se a diferença total passar de 0,1%, pare aqui:** não troque a base e registre no Estado.
- [ ] **M5.C5 Trocar a fonte.**
  - Etapa 1 do notebook lê o consolidado de 24 meses.
  - No `requirements.md`: R1 e R2.8 (fonte e período) e R2.10. A premissa R8.3a passa de "exclusões aplicadas na origem" para "MOV + FOR − EXC reconstruído e validado". O README também.
- [ ] **M5.C6 [painel] Aceleração por blocos.**
  - `bloco` derivado de `mes`: anterior = 202409–202508, recente = 202509–202608. O painel abre filtrado no **bloco recente**, então as outras métricas continuam sendo de 12 meses.
  - Aceleração = variação relativa do recente − a do anterior. O denominador é o estoque de 31/12/2025 se o M4 entrou; se não, saldo ÷ movimentações de cada bloco.
  - A aceleração volta ao Dinamismo com peso igual. Seletor "12 meses · 24 meses" só se sobrar tempo.

**Pronto quando:** o portão do C4 passou, a aceleração vem dos blocos 12 × 12, os salários estão deflacionados e `pytest -q` está verde.

---

## M6 · Validação contra as tabelas oficiais

**Branch:** `m6-validacao` · **Dono:** pessoa 5 · **Estimativa:** 1,5 h · **Exige M0.C0**
**Estado:** não iniciado. O xlsx **não está no projeto**.

- [ ] **H2 (humano)** Baixar as tabelas do Novo CAGED de set/2026 (página do PDET/MTE) e salvar em `docs/docs_admissao/09-2026/`, versionado.
- [ ] **M6.C1 `src/validacao.py`.**
  - Lê as Tabelas 7.1 (SC) e 8.1 (municípios) e compara admissões, desligamentos e saldo por mês com o nosso consolidado (24 meses se o M5 entrou, 12 se não).
  - Grava `data_processed/validacao_oficial.csv` com a diferença em %.
  - Testar só a função de comparação.
- [ ] **M6.C2 [painel] Metodologia.** Publicar a tabela de validação e tirar de "Próximos passos" o que foi feito.
- [ ] **M6.C3 (opcional)** Tabela 6.1, SC × Brasil por seção, alimentando a causa "Estrutural" (PLANEJAMENTO §7.2).

**Pronto quando:** a tabela de validação aparece na Metodologia, com as diferenças explicadas.

---

## M7 · Integração, deploy e congelamento (19h–22h)

**Branch:** `dashboard-v2` · **Dono:** pessoa 1, com apoio de todos
**Estado:** não iniciado

- [ ] **M7.C1** Rodar o notebook completo do zero com tudo que foi mergeado, gerando `metadados.json` com o commit. `pytest -q` verde.
- [ ] **M7.C2** Abrir o `streamlit run dashboard/app.py` local e clicar por todas as páginas, nos temas claro e escuro.
- [ ] **M7.C3** Subir no Blob **juntos** o agregado, o perfil, o `rais_estoque` e o `metadados`, porque o painel recusa schema misturado. Fazer o deploy no App Service (README) e o smoke test na URL pública. Abrir a URL uma vez antes do pitch, por causa da partida a frio.
- [ ] **M7.C4** Atualizar o `PLANEJAMENTO.md`:
  - decisões alteradas: D4 (IA por API e por arquivo), D8 (Azure) e §8.2 (taxonomia);
  - fechar as pendências do §16;
  - lista de "Próximos passos": RAIS 2024 e estoque mensal rolado, bootstrap e Mann-Whitney, clusters, 6 notebooks, além do que ficou no corte das 18h.
- [ ] **M7.C5** 22h: `git tag entrega-v1` e congelar o código.

---

## Fora do código (pessoa 5, em paralelo)

Slides e roteiro do pitch (PLANEJAMENTO §11). Os números finais entram depois do M7.C1.
O gancho "1 em cada 3" só pode ser usado se o M4 entrar. Se não entrar, use a saída voluntária (47,7% na indústria) e a compressão salarial (0,94, chegando a 0,89 no nível superior).
