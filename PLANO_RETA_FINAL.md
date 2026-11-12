# Plano da reta final: marcos e ciclos (12/11/2026)

**Prazo (PLANEJAMENTO §14):** código congelado hoje às **22h**, entrega em 13/11 às 08:30 e pitch às 10:30.
**Ponto de partida:** `dashboard-v2` em `717ce13`, com 232 testes verdes (`pytest -q`, cerca de 2,5 min).
**Base deste plano:** o parecer "Realinhamento do Raio-X SC", conferido contra o código. Os três problemas de método foram confirmados e os números batem.
As estimativas de tempo são chutes, servem para decidir o corte das 18h.

### Progresso (atualize a cada ciclo; é o primeiro lugar que a IA de cada um deve ler)

| Marco | Situação | Onde está | Último ciclo feito |
|---|---|---|---|
| M0 | **concluído** (C0 liberado pela equipe em 12/11) | `dashboard-v2` | M0.C0 |
| M1 | **concluído e mergeado** | `dashboard-v2` | M1.C5 |
| M2 | C1–C3 e H1 em `dashboard-v2`; concordância com o Gemini 91,4% (família) e 92,2% (nível); C4 feito (20 divergências aceitas); M2 **concluído** (C5 só se M4/M5 trouxerem CBOs novos) | `dashboard-v2` | M2.C4 |
| M3 | **mergeado** (C1–C4, C6, C7); **C5 (mapa) suspenso** | `dashboard-v2` | M3.C7 |
| M4 | **concluído e mergeado** (C1–C6; C7 opcional) | `dashboard-v2` | M4.C6 |
| M5 | **concluído e mergeado** (C1–C6) | `dashboard-v2` | M5.C6 |
| M6 | falta o H2 (xlsx do PDET) | — | — |
| M7 | não iniciado | — | — |

Commits locais só sobem com autorização do João: confira `git log origin/dashboard-v2..` antes de supor que algo foi publicado.

### Fila sem dependência humana (12/11, ~14h20)

Tudo isto pode ser feito por quem estiver livre, ou pela IA, sem esperar ninguém. Faça nas branches dos marcos e **não mergeie** M4, M5 ou M6 antes do M0.C0.

1. **M5.C1:** iniciar o download do CAGED de 24 meses em segundo plano (cerca de 1,3 GB) antes de qualquer outra coisa.
2. **M4.C3** (branch `m4-rais`): gerar o estoque por recorte a partir de `data/interim/rais_sc_2025.parquet`. Quem não tem o parquet roda `python scripts/baixar_rais.py && python -m src.rais` (cerca de 15 min). Os cuidados estão no Estado do M4 *na branch `m4-rais`*: seção derivada da subclasse e transferências (30–34) fora dos desligados.
3. **M4.C4:** coluna `desligamentos_descontados` no agregador, com código e testes. A reagregação precisa do `Dados/Novo_Caged_MOV_Limpo.csv` e fica para o M7.C1.
4. **M5.C2:** INPC (SIDRA → `data_processed/inpc.csv`, deflator e teste).
5. **M5.C3 e M6 (H2 + C1):** leitura do CAGED de 24 meses; baixar o xlsx do PDET e escrever `src/validacao.py`.

**Depende de alguém:**
- **M0.C0 (organizadores):** decide se M4, M5 e M6 entram no painel e no pitch.
- **Dono do painel:** os ciclos [painel] (M4.C5–C6, M5.C6, M6.C2).
- **M2.H1:** alguém roda os 23 prompts, ou a equipe decide que a IA da sessão (Claude) pode classificar a partir dos mesmos prompts. Se for a IA, registre isso na Metodologia.
- **João:** liberar o M3.C5 (mapa), os merges e o deploy (M7).
- **Arquivo `Dados/Novo_Caged_MOV_Limpo.csv`:** precisa estar na máquina que rodar o M5.C4 e o M7.C1.

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

- [x] **M0.C0 (humano), bloqueia M4, M5 e M6.** Confirmar com os organizadores se dados públicos externos (FTP do MTE, RAIS, IBGE) são permitidos (PLANEJAMENTO §16). Registre a resposta aqui. Se for não, M4, M5 e M6 saem do plano.
  - **Resposta (12/11, João):** liberado pela equipe. O Guia do Participante (`Instrucoes/`) não proíbe dados externos: o item 3 só lista o que a organização fornece; o item 2 pede "microdados públicos brutos" do Novo CAGED de SC, e o M5 é a mesma fonte, direto do MTE; a tabela de papéis pede "a filtragem das exclusões (MOV x EX)", que o M5 reconstrói; a RAIS (M4) é a única fonte do estoque, sem o qual não há rotatividade oficial, sinal de apagão citado no item 2.1. Cuidado de banca: o painel abre no bloco recente (os mesmos 12 meses da base fornecida) e a Metodologia cita as fontes externas como complemento.
  - **Dono do painel:** João (ciclos [painel] de M3–M6).
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
**Estado:** C1–C2 (e o C3 preparado) **mergeados em `dashboard-v2`** pelo PR #1 (`8ba7695`); os próximos ciclos podem sair direto de `dashboard-v2`. Prompts prontos em `ia_cbo/prompts/` (23 lotes, 2.207 CBOs, ≤ 100 por lote). C1 feito (`LLM_PROVIDER=arquivo`, sem `LLM_API_KEY`; com lote faltando, o erro lista quais). **H1 feito** na branch `m2-h1` (12/11): os 23 prompts foram respondidos pelo **Claude Opus 5.5 (`claude-opus-5-5`)**, a IA da sessão, a partir dos mesmos prompts, sem consultar o CSV do Gemini (a concordância continua válida). Conferência do COMO_USAR passo 4: 100 por lote, 7 no lote 23, **2.207 no total**; o `ClienteArquivo` carrega os 23 sem erro. Resultado: 623 códigos fogem da sugestão do prompt, todos com justificativa. Critérios que valem revisão no C4: CBO 766 (gráfica) em Operação de linha e processo, e não em Têxtil; ocupações elementares em Básico (125); auxiliares de saúde do grupo 3 em Qualificado; gerentes e diretores em Superior, na família da área dirigida. **Para o C3:** `LLM_MODELO_MANUAL=claude-opus-5-5` e registrar na Metodologia "classificação feita pelo Claude Opus 5.5 a partir dos mesmos prompts". C2 feito (`cbo_macrofamilias_gemini.csv` versionado; no modo arquivo a rodada 2 é esse CSV; a página de ocupações mostra o que foi comparado). C3 **preparado e não executado**: o README (Opção C), o `requirements.md` (R5.7, R5.9, R5.10 novo e R8.6) e o notebook (`PULAR_UPLOAD=1`) estão prontos; o comando está em `ia_cbo/COMO_USAR.md`, passo 5. O fluxo foi testado com respostas simuladas. **C3 feito** (12/11, com `LLM_MODELO_MANUAL=claude-opus-5-5`): o `meta.json` registra `ClienteArquivo`, 2.206 CBOs comparados, **concordância com o Gemini de 91,4% na família e 92,2% no nível**; `cbo_divergencias.csv` tem 348 linhas; agregado e perfil regenerados; `pytest -q` com 241 verdes. **C4 feito** (12/11): o João revisou as 20 divergências de maior volume e **aceitou todas como estão** (a classificação nova, r1, prevalece; nenhum JSON alterado). Destaques: frentista, vigia, porteiro e trabalhadores agrícolas/florestais em Básico (o Gemini dava Qualificado); encanador em Construção civil; técnico em segurança do trabalho em Engenharia/técnicos. M2 concluído; o C5 não é necessário (o M4 achou só 0,02% do estoque sem macrofamília). C5 só se o M4/M5 trouxer CBOs novos. Obs.: houve 1 falha intermitente na suíte completa que não se repetiu em 3 execuções (provável teste instável que já existia)

- [x] **H1 (humano)** Rodar os 23 prompts na IA paga e salvar em `ia_cbo/respostas/lote_NN.json`. O passo a passo, o formato e a conferência estão em `ia_cbo/COMO_USAR.md`.
- [x] **M2.C1 `ClienteArquivo` em `src/cbo_ia.py`.**
  - Implementa `ClienteLLM`. No `__init__`, junta todos os `respostas/lote_*.json` com `_extrair_mapeamento`. `classificar()` devolve `json.dumps(dict_inteiro)`, porque `classificar_lote` já filtra os códigos do lote.
  - Se faltar a resposta de algum `prompts/lote_NN.txt`, levanta `ErroDeValidacao` listando os lotes faltantes.
  - Em `criar_cliente_llm`, adicionar `LLM_PROVIDER=arquivo`, sem exigir `LLM_API_KEY`. O nome do modelo vem de `LLM_MODELO_MANUAL`.
  - Teste novo: `tests/test_cbo_ia_arquivo.py` (junta dois arquivos; um lote faltante dá erro).
- [x] **M2.C2 Concordância Gemini × IA paga.**
  - Copiar o `data_processed/cbo_macrofamilias.csv` atual para `cbo_macrofamilias_gemini.csv`.
  - Com o provedor `arquivo`, a rodada 2 compara com esse CSV, e não com a reexecução embaralhada (que daria 100% trivialmente). Usar `_registrar_concordancia`.
  - O `meta.json` registra o provedor, o modelo e a nota "classificação via chat; prompts e respostas em `ia_cbo/`".
- [x] **M2.C3 Reclassificar e reagregar** (depois do H1).
  - Rodar as etapas 5 e 6 do notebook com `LLM_PROVIDER=arquivo`.
  - No `requirements.md`, R5.7, R5.9 e R8.6 passam a valer só para os provedores por API, e entra um critério novo para o modo arquivo. README ganha uma seção "classificação via chat".
- [x] **M2.C4 Revisão humana** (parecer F4): revisar as 20 divergências de maior volume em `cbo_divergencias.csv`. Para corrigir, edite o `lote_NN.json`, com justificativa começando por "Revisão humana:", e rode o C3 de novo.
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
**Estado:** C1 feito na branch `m4-rais` (`python scripts/baixar_rais.py`, retomável; cerca de 12 min a 1 MB/s; extrai com `7z` ou, se não houver, com `bsdtar`). C2 feito: `python -m src.rais` grava `data/interim/rais_sc_2025.parquet` (cerca de 95 s, 51 MB): **4.290.964 vínculos CLT de SC, 295 municípios, 2.565.458 ativos em 31/12, 1.725.506 desligados no ano** (68,5% com menos de 12 meses de casa). C4 feito e **já reagregado** (o `Dados/Novo_Caged_MOV_Limpo.csv` estava na máquina do João): SC tem 1.674.947 desligamentos, dos quais 881.889 descontados; min(adm, desl_desc) ÷ estoque RAIS ≈ 34,4% (oficial 33,6%). O agregado e o perfil foram regenerados (somem `turnover`/`indice_aquecimento`). C3 feito: `python -m src.rais --estoque` grava `data_processed/rais_estoque.parquet` (61.484 linhas, chaves do agregado sem `mes`): estoque 2.565.458, `desligados_rais` 1.559.914 (sem transferências 30–34), precoce 1.073.959 (68,8%), médio completo ou mais 1.951.665; só 0,02% do estoque sem macrofamília (M2.C5 não é necessário); todas as seções batem com as do agregado. A escolaridade da RAIS não tem ignorados em SC CLT, mas `estoque_escolaridade_informada` fica como denominador. C5 feito: o painel anexa o estoque a cada célula na carga e soma **uma vez por célula distinta** (como a população), então todas as páginas e filtros funcionam sem mudança; métricas `rotatividade_desc`, `variacao_rel` e `precoce` em `agregar_metricas`. SC: rotatividade descontada **34,8%** (oficial 33,6%), Transformação 27,4% (Brasil 27,6%), precoce 69,0%. O estoque visível é 2.537.443 (−1,1%: células sem movimentação no período). O notebook sobe o `rais_estoque.parquet` junto no Blob. C6 feito: Tensão = rotatividade descontada + saída voluntária + precoce (pesos iguais, expander de sensibilidade de volta); Dinamismo = variação do emprego; tema Tensão do Panorama com a referência oficial ao lado; ranking de seções com a rotatividade; Metodologia explica o estoque de 31/12/2025 como aproximação do estoque médio. Checagem: SC 34,8% × 33,6% oficial. **Pronto quando: cumprido; mergeado em `dashboard-v2` (12/11).** C7 é opcional. Cuidados que valeram para o C3:
  - a RAIS **não tem a letra da seção**, só a subclasse CNAE de 7 dígitos: a seção sai da subclasse (divisão = 2 primeiros dígitos → seção CNAE);
  - os desligamentos da RAIS incluem **31 = transferência sem ônus (165 mil)**, que não é desligamento de verdade; decida se `desligados_rais` exclui os códigos 30–34 (recomendado) e registre na Metodologia. O código 90 (16 mil) não aparece no layout;
  - a escolaridade "médio completo ou mais" é `escolaridade >= 7` (−1 = ignorado, fora do denominador).
  O que o C1 encontrou, **conferido no layout `RAIS_vinculos_layout.xls` e no próprio arquivo**:
  - O arquivo extraído é `data/raw/rais/2025/RAIS_VINC_PUB_SUL.COMT` (4,3 GB, PR+SC+RS). **Separador `,`** (o layout diz `;`, mas está errado para 2025), **encoding Latin-1**, decimal `.`, cabeçalho entre aspas e alguns códigos entre aspas com espaço à esquerda (`" 4772500"`): use `dtype=str` e `.str.strip()`.
  - Colunas que o M4 usa: `Município - Código` (6 dígitos; SC começa com `42`), `Tipo Vínculo - Código`, `Ind Vínculo Ativo 31/12 - Código` (0 = não, 1 = sim), `Motivo Desligamento - Código` (0 = não desligado no ano), `Mês Desligamento - Código` (0 = não desligado), `Tempo Emprego` (em **meses**, com decimal), `Escolaridade Após 2005 - Código` (1–11, médio completo = 7; −1 = ignorado), `CBO 2002 Ocupação - Código`, `CNAE 2.0 Subclasse - Codigo` (sem acento no "Codigo"), `Vl Rem Média Nom`.
  - `Tipo Vínculo` CLT segundo o layout: **10, 15, 20, 25** (prazo indeterminado) e **60, 65, 70, 75** (prazo determinado). Ficam de fora: 30–35 (estatutário), 40 (avulso), 50 (temporário), 55 (aprendiz), 80 (diretor) e 90–97. Decisão para o C2: usar só esses oito códigos CLT; aprendiz e temporário ficam fora, e isso vai para a Metodologia.
  - Os códigos de desligamento da RAIS **não são os do CAGED**: 10/11 = demissão com/sem justa causa, 12 = término de contrato, 20/21 = a pedido (com/sem justa causa), 30–34 = transferência, 60–64 = falecimento, 70–80 = aposentadoria. Não reaproveite o "40 = a pedido" do CAGED aqui.

**Ideia central:** **só a RAIS 2025.** O estoque em 31/12/2025 cai dentro da janela set/25–ago/26 e serve de aproximação do estoque médio. Assim saem a rotatividade descontada (PLANEJAMENTO §6), a variação relativa (saldo ÷ estoque), o desligamento precoce e o gap de escolaridade contra o estoque. A RAIS 2024 e o estoque mensal rolado ficam para depois.

- [x] **M4.C1 Baixar e inspecionar** (mergeável sozinho).
  - Script que baixa para `data/raw/rais/2025/`, retomável (pula o que já existe), e extrai com `7z`.
  - Baixar também o layout da RAIS no FTP e anotar no Estado: nomes das colunas, separador, encoding e os códigos de `Tipo Vínculo` CLT e de `Vínculo Ativo 31/12`. **Conferir no layout, não de memória.**
- [x] **M4.C2 `src/rais.py: ler_rais_sc()`.**
  - Leitura em `chunksize`, filtrando município de SC (6 dígitos começando com 42) e vínculos CLT. Manter só as colunas necessárias.
  - Grava `data/interim/rais_sc_2025.parquet`.
  - Um teste com um CSV sintético de 5 linhas.
- [x] **M4.C3 `estoque_rais()` → `data_processed/rais_estoque.parquet`.**
  - Chaves iguais às do agregado, **sem `mes`**.
  - Colunas: `estoque_31dez`, `estoque_medio_ou_mais` (médio completo ou mais), `desligados_rais` e `desligados_precoce` (menos de 12 meses de casa).
  - Reaproveitar o mapeamento subclasse → seção/setor do `agregador.py` e o `aplicar_mapeamento` dos CBOs.
  - Registrar a % do estoque em CBOs sem macrofamília; se passar de 1%, acionar o M2.C5.
- [x] **M4.C4 Desligamentos descontados no CAGED.**
  - Nova coluna aditiva `desligamentos_descontados` em `src/agregador.py` (`COLUNAS_ADITIVAS` e `preparar_base`): desligamentos menos os códigos 40, 50, 60 e 80 (PLANEJAMENTO §6).
  - Atualizar a checagem de schema e reagregar.
  - ⚠️ O M5.C3 mexe na mesma função. Quem mergear por último faz o rebase.
- [x] **M4.C5 [painel] Carregar o estoque.**
  - `rais_estoque.parquet` entra em `carregar_artefatos` (local e Blob, com novo `NOME_BLOB_*`) e no schema.
  - Em `agregar_metricas`, o estoque é somado pelos mesmos `por` e anexado. **Nunca replicar o estoque nas linhas mensais.**
  - Métricas novas: `rotatividade_desc = min(adm, desl_desc) / estoque`, `variacao_rel = saldo / estoque` e `precoce = desligados_precoce / desligados_rais`.
- [x] **M4.C6 [painel] Índice e KPIs.**
  - Tensão = rotatividade descontada + saída voluntária + precoce, com pesos iguais e o expander de sensibilidade de volta. Dinamismo = variação relativa.
  - KPI de rotatividade ao lado da referência oficial (SC 33,6%, Brasil 34,2%, Transformação Brasil 27,6%; PLANEJAMENTO §6).
  - **Checagem:** a rotatividade de SC com todas as seções tem que ficar perto de 33,6%. Se ficar longe, investigar antes de publicar.
- [ ] **M4.C7 (opcional)** Gap de escolaridade contra o estoque (no lugar de admitidos − desligados) e recomendação "desligamento precoce → integração nos primeiros 90 dias" (parecer F6).

**Pronto quando:** a rotatividade descontada aparece no Panorama ao lado da referência oficial, o índice tem os 3 sintomas, a Metodologia explica "estoque de 31/12/2025 como aproximação do estoque médio" e `pytest -q` está verde.

---

## M5 · CAGED 24 meses (MOV + FOR − EXC) e INPC

**Branch:** `m5-caged24` · **Dono:** pessoa 3 e pessoa 1 no [painel] · **Estimativa:** 4 a 5 h · **Exige M0.C0**
**Estado:** C1 feito: `python -m src.download` baixa os 72 `.7z` (MOV/FOR/EXC, 202409–202608) para `data/raw/caged/`, retomável (rode de novo se cair). C2 feito: `python -m src.inpc` regrava `data_processed/inpc.csv` (202409–202608); `limpar()` deflaciona o `salário` a preços de ago/2026 logo depois do filtro de competência (todo salário do painel passa a ser real). C3 feito: `python -m src.caged24` (cerca de 7 min) lê os `.7z` direto do `7z e -so` (nenhum `.txt` no disco) e grava `data/interim/caged_sc_24m.parquet`: 6.782.144 linhas de SC (MOV 6.715.601, FOR 61.317, EXC 5.226), tudo como texto mais `peso` e `tipo_arquivo`. FOR/EXC publicados depois de 202608 ficam de fora, como na base fornecida. ⚠️ **Para o C4:** a prévia do bloco recente mostra que a base fornecida bate com **MOV + FOR − EXC** (adm 1.716.676 × 1.716.341; desl 1.675.038 × 1.674.947: +0,02%), e **não** com só o MOV (1.701.471 / 1.661.268: −0,9%). C4 feito: `python -m src.caged24 --validar` grava `data_processed/validacao_base_fornecida.csv` (mês × município, bloco recente) com as duas leituras. **MOV + FOR − EXC: adm +0,020%, desl +0,005%** (142 de 3.539 células diferem, 426 movimentações; o excesso some até 202608, compatível com declarações fora do prazo que chegaram depois da extração da base fornecida) → **passa**. Só MOV: adm −0,87%, desl −0,82% → reprovaria; ou seja, a base fornecida já é MOV + FOR − EXC. C5 feito: o notebook usa `data/interim/caged_sc_24m.parquet` quando existe (`FONTE_CAGED=fornecida` volta à base de 12 meses), com a janela 202409–202608; o `peso` entra no `saldo_liquido` e em todas as contagens e somas do `preparar_base` (nas medianas do perfil, a linha EXC sai sozinha). Agregado: 511.621 linhas; bloco recente **adm 1.716.676 e desl 1.675.038, iguais à validação**; bloco anterior adm 1.726.752, desl 1.653.226. ⚠️ **Memória:** com 6,8 mi de linhas, o pipeline passava de 7 GB e foi morto pelo sistema (derrubou a IDE do João). Correções: leitura só das 16 colunas usadas, texto como `category`, cópias rasas (copy-on-write) na limpeza, decodificação por valor distinto e o notebook liberando a base bruta. Pico agora ≈ 6,5 GB; rode o notebook **sem outros processos pesados** (ou com `systemd-run --user --scope -p MemoryMax=7500M`). C6 feito: o painel abre em set/25–ago/26 (`periodo_padrao`); `anexar_blocos` põe em cada célula o saldo de cada bloco, e a aceleração = (saldo recente − anterior) ÷ estoque, em p.p., sai igual com qualquer filtro de período; Dinamismo = variação do emprego + aceleração, com pesos iguais; a Metodologia descreve 24 meses, a validação, o INPC e os blocos. SC (toda a economia): saldo 41.638 contra 73.526 no ano anterior → aceleração −1,4 p.p.; indústria −1,8 p.p. **Pronto quando: cumprido.** ⚠️ O critério do portão foi trocado de "só o MOV" para MOV + FOR − EXC por esse motivo: confirme com a equipe antes do C5. O FTP já tem até 202609, mas a janela continua **set/24–ago/26** (D1), para bater com a base fornecida. ⚠️ O portão do C4 precisa do `Dados/Novo_Caged_MOV_Limpo.csv`, que é ignorado pelo Git e **não está em todas as máquinas** (não está no codespace de 12/11): consiga o arquivo antes de começar. ⚠️ O `7z` não está instalado no codespace; o `bsdtar` (libarchive) é a alternativa já presente.

- [x] **M5.C1 `src/download.py`** (mergeável sozinho).
  - Baixa `NOVO CAGED/AAAA/AAAAMM/CAGED{MOV,FOR,EXC}AAAAMM.7z` de 202409 a 202608 (72 arquivos, cerca de 1,3 GB) para `data/raw/caged/`, de forma retomável.
  - **Deixe rodando em segundo plano** e siga para o C2.
- [x] **M5.C2 INPC** (mergeável sozinho).
  - `src/inpc.py` busca o SIDRA (tabela 1736, variável 44) e grava `data_processed/inpc.csv`, versionado, para o pipeline rodar offline.
  - Em `src/limpeza.py`, deflacionar o `salário` para preços de ago/2026.
  - Teste: o fator de 202608 é 1.
- [x] **M5.C3 Ler e consolidar.**
  - Extrair um arquivo por vez com `7z`, ler com `chunksize` (separador `;`, decimal `,`), filtrar `uf == 42` e apagar o `.txt`.
  - Coluna `peso`: +1 para MOV e FOR, **−1 para EXC**, mantendo o tipo. Admissões e desligamentos são a soma de `peso` por tipo, e o saldo é Σ `peso × saldomovimentação`.
  - Filtrar por `competênciamov` dentro da janela. Grava `data/interim/caged_sc_24m.parquet`.
- [x] **M5.C4 Validar a leitura (portão).** *(feito comparando MOV + FOR − EXC; ver Estado)*
  - Bloco recente, **só o MOV**, contra `Dados/Novo_Caged_MOV_Limpo.csv`, por mês × município × (adm, desl). Grava `data_processed/validacao_base_fornecida.csv`.
  - **Se a diferença total passar de 0,1%, pare aqui:** não troque a base e registre no Estado.
- [x] **M5.C5 Trocar a fonte.**
  - Etapa 1 do notebook lê o consolidado de 24 meses.
  - No `requirements.md`: R1 e R2.8 (fonte e período) e R2.10. A premissa R8.3a passa de "exclusões aplicadas na origem" para "MOV + FOR − EXC reconstruído e validado". O README também.
- [x] **M5.C6 [painel] Aceleração por blocos.**
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
