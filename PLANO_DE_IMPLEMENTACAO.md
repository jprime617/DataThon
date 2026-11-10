# Plano de Implementação — Datathon CDIA 2026

## Raio-X do Mercado de Trabalho e Vagas Industriais em Santa Catarina

---

## 1. Entendimento do desafio

**Pergunta central de negócio:**
> "Quais regiões e setores industriais de Santa Catarina estão enfrentando apagão de mão de obra ou expansão acelerada, e como os indicadores de renda e escolaridade explicam esses gargalos?"

**Papel:** consultoria de dados contratada por uma entidade de classe (ex.: Federação das Indústrias) ou grupo empresarial.

**Entregáveis obrigatórios:**
1. Notebook/Script (`.ipynb` ou `.py`) com todo o pipeline documentado.
2. Dashboard analítico em Python (Streamlit/Plotly) com **no mínimo 3 KPIs**.
3. Pitch executivo de 3 minutos (slides).
4. Tudo em repositório Git público.

**Critérios de avaliação:** compreensão do problema industrial · embasamento analítico · dashboard e storytelling · recomendações de valor · pitch.

---

## 2. Conferência dos dados (feita)

### 2.1. `Novo_Caged_MOV_Limpo.csv`
- **Volume:** ~3.397.416 linhas · separador `;` · decimal com vírgula (`2018,00`).
- **Período:** concentrado em **set/2025 → ago/2026** (12 meses). Há poucos registros residuais de meses anteriores (declarações fora do prazo) — tratar via filtro de competência.
- **UF:** única = `42` (Santa Catarina). ✔
- **Colunas-chave:** `competênciamov`, `município`, `seção` (CNAE), `subclasse`, `saldomovimentação` (+1 admissão / -1 desligamento), `cbo2002ocupação`, `graudeinstrução`, `idade`, `raçacor`, `sexo`, `salário`, `valorsaláriofixo`, `tamestabjan`.
- **Seções CNAE presentes:** A–T e Z (21 seções). Indústria = foco em **C** (transformação), com apoio de B (extrativa), D, E, F.
- **Colunas descartáveis:** `Unnamed: 0.1`, `Unnamed: 0` (índices residuais).

> ⚠️ **Premissa sobre as exclusões (MOV x EX):** o dicionário descreve `indicadordeexclusão` e `competênciaexc`, mas **essas colunas não existem neste arquivo** — ele já vem com as exclusões aplicadas ("Limpo"). A etapa de "filtro EX" do guia deve ser documentada como já realizada na origem.

### 2.2. `Municipios_SC_limpo.csv`
- **Volume:** 296 municípios · separador `,`.
- **Colunas:** `Município`, `Código` (IBGE 7 díg.), `Gentílico`, `Prefeito`, `Área km²`, `População censo 2022`, `Densidade`, `População estimada 2026`, `Escolarização 6-14`, `IDHM 2010`, `Mortalidade infantil`, `Receitas`, `Despesas`, `PIB per capita 2023`.
- **Qualidade:** há valores ausentes marcados como `-` (ex.: mortalidade infantil) → converter para `NaN`. Números em formato brasileiro.

### 2.3. Chave de junção (ponto crítico)
- CAGED: `município` = **6 dígitos** (ex.: `420890`).
- Municípios: `Código` = **7 dígitos** IBGE (ex.: `4200051`).
- **Solução:** normalizar — o 7º dígito do IBGE é verificador; usar os 6 primeiros dígitos (`Código // 10` ou `str[:6]`) como chave comum.

### 2.4. Tabelas de domínio a decodificar (do dicionário)
`graudeinstrução`, `raçacor`, `sexo`, `tipomovimentação`, `categoria`, `tamestabjan`, `unidadesaláriocódigo`, seções CNAE. Criar dicionários de mapeamento para rótulos legíveis.

---

## 3. Arquitetura da solução

```
DataThon/
├── Dados/                      # fontes originais (não versionar o CSV gigante cru; usar Git LFS ou .gitignore)
├── notebooks/
│   └── 01_pipeline.ipynb       # pipeline documentado end-to-end
├── src/
│   ├── ingestao.py             # carga + schema + tipos
│   ├── limpeza.py              # tratamento de nulos, normalização de chaves
│   ├── enriquecimento.py       # join CAGED x municípios + métricas
│   ├── cbo_ia.py               # agrupamento de CBOs via LLM
│   └── mapeamentos.py          # dicionários de domínio
├── data_processed/
│   ├── caged_agregado.parquet  # agregações por município/setor/mês
│   └── cbo_macrofamilias.csv   # saída do enriquecimento IA
├── dashboard/
│   └── app.py                  # Streamlit
├── pitch/
│   └── pitch.pdf
├── requirements.txt
├── README.md
└── PLANO_DE_IMPLEMENTACAO.md
```

**Stack:** Polars ou Pandas (pyarrow) para ler 3.4M linhas · Plotly/Seaborn para gráficos · Streamlit para o dashboard · API de LLM (OpenAI/Gemini) para agrupar CBOs.

> Dica de performance: converter o CSV para **Parquet** logo na ingestão; a leitura cai de segundos para milissegundos nas iterações seguintes.

---

## 4. Pipeline de dados (etapas)

### Etapa 1 — Ingestão e validação
- Ler CSV com `sep=";"`, `decimal=","`, dtypes explícitos para colunas categóricas.
- Dropar `Unnamed: *`.
- Validar schema contra o dicionário; conferir UF única = 42.

### Etapa 2 — Limpeza e tratamento
- Converter `salário`/`valorsaláriofixo` para float (vírgula → ponto).
- Filtrar competências ao range alvo (set/2025–ago/2026) ou manter tudo e documentar.
- Decodificar domínios (grau de instrução, sexo, raça/cor, seção CNAE) via `mapeamentos.py`.
- Tratar `-` → NaN no arquivo de municípios; converter números BR.

### Etapa 3 — Cruzamento relacional (join)
- Normalizar chave municipal (6 dígitos) nos dois lados.
- `merge` CAGED × municípios por código.
- Validar perda de match (municípios sem correspondência).

### Etapa 4 — Métricas de negócio
- **Saldo líquido** = Σ `saldomovimentação` por recorte (município × setor × mês).
- **Saldo por 10.000 habitantes** = (saldo / população estimada 2026) × 10.000 — normaliza a comparação entre cidades (pedido explícito no guia).
- **Rotatividade / turnover** = min(admissões, desligamentos) / estoque base — proxy de "apagão".
- **Salário médio de admissão vs desligamento** por setor — detecta compressão salarial.
- **Perfil de escolaridade** dos admitidos vs desligados.
- **Índice de aquecimento:** combinar saldo relativo + crescimento mês a mês para separar "expansão acelerada" de "apagão".

### Etapa 5 — Enriquecimento com IA (agrupamento de CBOs)
- Extrair a lista única de CBOs (centenas de códigos).
- Prompt a um LLM para agrupar em **macrofamílias** (ex.: Engenharia/Técnico, Operacional de Produção, Administrativo, Logística, TI).
- Salvar o mapeamento `cbo → macrofamília` em CSV e fazer merge na base.
- Documentar o prompt e validar amostras manualmente (transparência de premissas).

### Etapa 6 — Agregações finais
- Tabelas por: região/microrregião × setor industrial × macrofamília × mês.
- Exportar para Parquet/CSV consumidos pelo dashboard.

---

## 5. Dashboard (mínimo 3 KPIs)

Narrativa: **Localizar o problema → Entender a causa raiz → Decidir.**

1. **Mapa coroplético de SC** — saldo por 10.000 hab. por município (vermelho = encolhimento / verde = expansão).
2. **Ranking de setores industriais** — barras com saldo líquido e turnover; destaque para seção C.
3. **Dispersão renda × escolaridade** — salário médio de admissão vs grau de instrução, por setor/macrofamília, revelando gargalos.
4. (Bônus) Série temporal do saldo mensal e filtro por macrofamília de CBO.

Filtros: período, região, setor (CNAE), macrofamília de CBO.

---

## 6. Pitch executivo (3 min)
- Contexto industrial de SC (têxtil Vale do Itajaí, metalmecânico Norte, agroindústria Oeste, eletroeletrônico/tech Grande Fpolis).
- 2–3 gargalos concretos (apagão vs expansão) com evidência de dados.
- Causa raiz: salário, escolaridade ou rotatividade.
- 2–3 recomendações acionáveis (formação direcionada, revisão salarial, atração de talentos).

---

## 7. Divisão de trabalho (equipe 5 pessoas: 2 de 4ª + 3 de 2ª fase)
| Frente | Responsável típico |
|---|---|
| Ingestão + limpeza + join | Técnico/Dados |
| Métrica saldo/10k hab + agregações | IA & Negócios |
| Enriquecimento CBO via LLM | IA & Negócios |
| Gráficos + dashboard Streamlit | Técnico/Dados |
| Narrativa + pitch | IA & Negócios |

---

## 8. Próximos passos imediatos
1. Criar `requirements.txt` e estrutura de pastas.
2. Implementar `ingestao.py` com conversão para Parquet e amostragem de validação.
3. Montar `mapeamentos.py` com as tabelas de domínio do dicionário.
4. Fazer o join e validar a chave municipal.
5. Prototipar o dashboard com dados agregados.

> **Riscos / premissas:** (a) exclusões já aplicadas na origem; (b) IDHM é de 2010 (desatualizado — usar com ressalva); (c) meses das pontas podem estar incompletos — considerar janela estável de 12 meses cheios; (d) volume de 3.4M linhas exige agregação antes do dashboard.
