# Datathon CAGED SC — Pipeline e Dashboard

Pipeline de dados e dashboard analítico do **Datathon CDIA 2026 — "Raio-X do Mercado de Trabalho e Vagas Industriais em Santa Catarina"**.

A solução responde à pergunta central de negócio: *quais regiões e setores industriais de SC enfrentam apagão de mão de obra ou expansão acelerada, e como os indicadores de renda e escolaridade explicam esses gargalos.*

O fluxo é linear: **ingestão → limpeza → cruzamento relacional → métricas de negócio → enriquecimento de CBOs via IA → agregação → upload Azure → dashboard**. O volume bruto (~3,4 milhões de linhas do CAGED movimentado de SC) é processado uma única vez no pipeline; o dashboard consome apenas tabelas agregadas de poucos MB.

## Fluxo completo (resumo)

Este é o caminho feliz ponta a ponta que um novo usuário segue. Cada passo é detalhado nas seções correspondentes mais abaixo.

1. Instalar **Python 3.11.9** (via pyenv) e criar o ambiente virtual (`.venv`) — ver [Pré-requisitos de ambiente](#pré-requisitos-de-ambiente).
2. Instalar as dependências: `pip install -r requirements.txt`.
3. Criar a conta de armazenamento no Azure e o container — ver [Passo 1 — Criar a conta de armazenamento no Azure](#passo-1--criar-a-conta-de-armazenamento-no-azure).
4. Obter a chave do Claude (Anthropic) — ver [Passo 2 — Obter a chave do Claude (Anthropic)](#passo-2--obter-a-chave-do-claude-anthropic).
5. Exportar as variáveis de ambiente — ver [Passo 3 — Exportar as variáveis de ambiente](#passo-3--exportar-as-variáveis-de-ambiente).
6. Executar o pipeline pelo notebook `notebooks/01_pipeline.ipynb`.
7. Iniciar o dashboard: `streamlit run dashboard/app.py`.

## Pré-requisitos de ambiente

- **Python 3.11.9** — versão de referência do projeto. Recomenda-se gerenciar a versão com [pyenv](https://github.com/pyenv/pyenv):

  ```bash
  pyenv install 3.11.9
  pyenv local 3.11.9
  python --version   # deve imprimir Python 3.11.9
  ```

- Ambiente virtual isolado (recomendado):

  ```bash
  python -m venv .venv
  source .venv/bin/activate        # Linux/macOS
  # .venv\Scripts\activate         # Windows (PowerShell)
  ```

- **Arquivos de origem** disponíveis em `Dados/`:
  - `Novo_Caged_MOV_Limpo.csv` — CAGED movimentado de SC (sep `;`, decimal `,`).
  - `Municipios_SC_limpo.csv` — 295 municípios de SC (sep `,`, **ponto decimal**; a última linha do arquivo é um rodapé de notas do IBGE, descartado pela junção).
  - `Dicionario_de_dados.xlsx` — domínios das variáveis categóricas.

- **Malha geográfica** `dashboard/geo/sc_municipios.geojson` para o mapa coroplético. Ela já vem versionada; para regenerá-la a partir da API de malhas do IBGE:

  ```bash
  python scripts/baixar_malha_sc.py
  ```

  O script baixa os 295 municípios de SC e reescreve a identificação das *features* para a Chave_Municipal de 6 dígitos usada pelo agregado.

- **Variáveis de ambiente** (veja a seção [Credenciais](#credenciais-e-segredos)):
  - `LLM_PROVIDER` — provedor do LLM externo: `gemini` (padrão, **gratuito**), `anthropic` ou `arquivo` (respostas coladas de uma IA via chat, sem chave; ver Opção C).
  - `LLM_API_KEY` — credencial da API do LLM externo (etapa de agrupamento de CBOs). Para o Gemini, obtida no [Google AI Studio](https://aistudio.google.com/apikey); para o Claude, no [Anthropic Console](https://console.anthropic.com).
  - `AZURE_STORAGE_CONNECTION_STRING` — acesso ao Azure Blob Storage (upload das tabelas agregadas e leitura pelo dashboard).

## Instalação das dependências

As dependências estão fixadas com versões exatas (sem faixas) em `requirements.txt`.

```bash
pip install -r requirements.txt
```

Bibliotecas principais: `pandas`, `pyarrow` (backend Parquet), `openpyxl` (leitura do `.xlsx`), `plotly` e `streamlit` (dashboard), `google-genai` e `anthropic` (SDKs do LLM externo), `azure-storage-blob` (upload Blob), além de `pytest` e `hypothesis` para os testes.

## Configuração de credenciais (passo a passo)

Esta seção é um tutorial do zero para obter as duas credenciais que o pipeline
exige: a connection string do Azure Blob Storage e a chave da API do Claude
(Anthropic). Siga os passos na ordem.

### Passo 1 — Criar a conta de armazenamento no Azure

1. Acessar <https://portal.azure.com> e entrar (use a assinatura **Azure for Students**, se aplicável).
2. **Create a resource** → buscar por **"Storage account"** → **Create**.
3. Na aba **Basics**, preencher:
   - **Subscription**: selecionar a assinatura (Azure for Students).
   - **Resource group**: criar um novo (ex.: `rg-datathon`).
   - **Storage account name**: um nome **único**, apenas letras minúsculas e números (ex.: `datathoncagedsc`).
   - **Region**: `Brazil South`.
   - **Performance**: `Standard`.
   - **Redundancy**: `LRS` (localmente redundante — a opção mais barata e SKU elegível para a conta de estudante).
4. **Review + create** → **Create** e aguardar a implantação concluir.
5. Abrir a conta criada → menu **Containers** → **+ Container** → criar um container chamado `caged-agregado`. Esse é o nome padrão que o notebook usa através da variável de ambiente `AZURE_BLOB_CONTAINER`; se você escolher outro nome, defina essa variável com o nome escolhido.
6. Pegar a **connection string**: na conta → **Security + networking** → **Access keys** → clicar em **Show** na `key1` → copiar o campo **"Connection string"** inteiro. Ele começa com `DefaultEndpointsProtocol=https;...;EndpointSuffix=core.windows.net`.
   - O guard do pipeline valida o prefixo `DefaultEndpointsProtocol=`, então copie a **string completa**, não apenas o valor da `AccountKey`.

### Passo 2 — Obter a chave do LLM externo

O agrupamento de CBOs em macrofamílias usa um LLM externo via API, executado localmente durante o pipeline (R5.9). Há dois provedores suportados; o adaptador correspondente vive em `src/cbo_ia.py` por trás da interface `ClienteLLM`, e a escolha é feita pela variável `LLM_PROVIDER`.

#### Opção A — Gemini (padrão, **gratuito**)

O Google AI Studio emite uma chave sem cartão de crédito, e a camada gratuita cobre com folga os ~23 lotes desta etapa.

1. Acessar <https://aistudio.google.com/apikey> e entrar com uma conta Google.
2. **Create API key** → copiar o valor. A chave começa com `AIza`.
3. Exportar:

   ```bash
   export LLM_PROVIDER=gemini
   export LLM_API_KEY="AIza..."
   ```

O modelo padrão é `gemini-3.1-flash-lite` (`MODELO_PADRAO_GEMINI` em `src/cbo_ia.py`).

#### Opção B — Claude (Anthropic)

1. Acessar <https://console.anthropic.com> e criar a conta ou entrar.
2. **Settings** → **API Keys** → **Create Key** → copiar o valor. A chave começa com `sk-ant-` e **só é exibida uma vez**.
3. Garantir saldo em **Settings** → **Billing**. Sem crédito, a API responde `400 — credit balance is too low`.
4. Exportar com `LLM_PROVIDER=anthropic`. O modelo padrão é `claude-opus-5` (`MODELO_PADRAO`).

#### Opção C — Classificação via chat (`LLM_PROVIDER=arquivo`, sem API)

Para usar uma IA paga sem acesso à API, os prompts já estão gerados em `ia_cbo/prompts/lote_NN.txt` (23 lotes, 2.207 CBOs).

1. Siga `ia_cbo/COMO_USAR.md`: cole cada prompt na IA e salve só o JSON da resposta em `ia_cbo/respostas/lote_NN.json`.
2. Rode a classificação a partir das respostas. **Não precisa de `LLM_API_KEY`.**

   ```bash
   export LLM_PROVIDER=arquivo LLM_MODELO_MANUAL="<nome do modelo usado no chat>" RECLASSIFICAR_CBO=1 PULAR_UPLOAD=1
   .venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/01_pipeline.ipynb
   ```

- Se faltar a resposta de algum lote, o pipeline para e lista os lotes que faltam. Se um arquivo vier sem JSON válido, ele diz qual.
- A concordância deixa de ser "a mesma IA com a ordem embaralhada", que daria 100% ao reler os mesmos arquivos. Ela passa a comparar a IA paga com a classificação anterior do Gemini, guardada em `data_processed/cbo_macrofamilias_gemini.csv`. As divergências vão para `data_processed/cbo_divergencias.csv`.
- O `cbo_macrofamilias.csv.meta.json` registra o provedor (`ClienteArquivo`), o modelo informado e a nota "classificação via chat; prompts e respostas em `ia_cbo/`".
- Para corrigir uma classificação após revisão humana, edite o `lote_NN.json` com uma justificativa começando por "Revisão humana:" e rode de novo.

#### Dois comportamentos que evitam o fracasso silencioso

- **Falha permanente** do provedor (saldo insuficiente, credencial inválida, modelo inexistente — HTTP 400/401/403/404) **interrompe o pipeline** com uma mensagem acionável, em vez de cair no fallback. Um modelo aposentado ou uma conta sem saldo faria *toda* chamada falhar e, sem essa proteção, o pipeline terminaria "com sucesso" classificando os 2.206 CBOs como `Não classificado`.
- Se ainda assim mais da metade dos CBOs cair no fallback, a etapa registra um **ALERTA** no log.

### Passo 3 — Exportar as variáveis de ambiente

Com as duas credenciais em mãos, exporte-as no shell antes de executar o pipeline:

```bash
export LLM_PROVIDER="gemini"                   # opcional; gemini já é o padrão
export LLM_API_KEY="AIza..."
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"
export AZURE_BLOB_CONTAINER="caged-agregado"   # opcional; default já é caged-agregado
```

Há um modelo pronto em `.env.example`. Copie para `.env` (que está no `.gitignore`) e carregue com:

```bash
set -a; source .env; set +a
```

> O **mesmo** `AZURE_BLOB_CONTAINER` é usado pelo pipeline no upload e pelo dashboard na leitura. Nomes divergentes fazem o dashboard não achar o blob e cair no fallback local silenciosamente.

> **Segurança:** nunca commite essas variáveis no repositório. Se preferir
> persistir os valores localmente, use um arquivo `.env` **não versionado**
> (adicionado ao `.gitignore`).

## Execução do pipeline

O pipeline roda ponta a ponta, sem intervenção manual entre etapas, pelo notebook orquestrador. Antes de executar, defina as variáveis de ambiente de credenciais (veja [Configuração de credenciais (passo a passo)](#configuração-de-credenciais-passo-a-passo) para o passo a passo completo de como obtê-las):

```bash
export LLM_PROVIDER="gemini"
export LLM_API_KEY="AIza..."
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"
```

Em seguida execute o notebook `notebooks/01_pipeline.ipynb`:

```bash
# Opção A — executar o notebook sem abrir a UI (headless)
jupyter nbconvert --to notebook --execute --inplace notebooks/01_pipeline.ipynb

# Opção B — abrir o Jupyter e executar as células interativamente
jupyter notebook notebooks/01_pipeline.ipynb
```

O pipeline executa em sequência: ingestão → limpeza → junção relacional → métricas → agrupamento de CBOs via LLM → agregação → upload para o Azure Blob Storage. Cada etapa registra uma mensagem de progresso única e produz os artefatos consumidos pelo dashboard em `data_processed/`:

| Artefato | Conteúdo | Vai para o Blob |
|---|---|---|
| `caged_agregado.parquet` | município × seção × setor × macrofamília × nível × mês, com as colunas R6 e as contagens/somas aditivas (`admissoes`, `desligamentos`, `desligamentos_a_pedido`, `soma_salario_*`, `n_salario_*`, `soma_escolaridade_*`, `n_escolaridade_*`) | sim |
| `caged_perfil.parquet` | mesorregião × setor × macrofamília × nível × faixa de escolaridade, período inteiro, com as **medianas** salariais | sim |
| `metadados.json` | procedência: data de geração, período, commit, volumes, IA (provedor, modelo, concordância) | sim |
| `cbo_macrofamilias.csv` (+ `.prompt.txt`, `.meta.json`) e `cbo_divergencias.csv` | classificação da IA, prompt exato e auditoria das duas rodadas | não — vão no pacote de deploy |

A classificação de CBO é reaproveitada do `cbo_macrofamilias.csv` quando ele existe; defina `RECLASSIFICAR_CBO=1` para chamar o LLM de novo.

Observações sobre credenciais durante a execução:

- Se `LLM_API_KEY` estiver ausente ou vazia, o pipeline interrompe **antes** de chamar a API do LLM, com mensagem de erro indicando que a credencial não foi fornecida.
- Se `AZURE_STORAGE_CONNECTION_STRING` estiver ausente ou inválida, a etapa de upload é interrompida **antes** de chamar o Azure, sem enviar dados parciais.

## Dashboard

O dashboard Streamlit consome as tabelas agregadas. Ele lê primeiro do Azure Blob Storage e, se este estiver indisponível, faz fallback para a cópia local em `data_processed/`.

```bash
streamlit run dashboard/app.py
```

Para habilitar a leitura a partir do Blob Storage, defina `AZURE_STORAGE_CONNECTION_STRING` antes de iniciar o app. Sem essa variável, o dashboard usa automaticamente a cópia local das tabelas agregadas.

O painel tem sete páginas na ordem da narrativa — **Panorama** (onde está o problema), **Diagnóstico** (matriz dinamismo × tensão), **Causa raiz** (salário, qualificação, retenção), **Ocupações (IA)** (macrofamílias, explorador de CBO e auditoria da IA), **Recomendações** (regras → alavancas, ficha da mesorregião em Markdown, custo da saída voluntária), **Ficha do território** e **Metodologia** — além do **Modo apresentação**, com os 5 passos do pitch. Os filtros da barra lateral (escopo, período, território, setor, macrofamília e nível) valem para todas as páginas. Todo número exibido é recalculado a partir das contagens aditivas do agregado (soma antes de dividir), com guarda de amostra: taxas exigem ≥ 100 movimentações; gaps salariais, ≥ 30 salários de cada lado.

Código: `dashboard/app.py` (navegação), `dashboard/comum.py` (dados, métricas, filtros, formatação, tema), `dashboard/figuras.py` (figuras puras), `dashboard/narrativa.py` (frases calculadas) e `dashboard/paginas/`.

## Implantação no Azure (App Service)

O dashboard roda no Azure App Service lendo as tabelas agregadas do Blob Storage, com *fallback* para a cópia local (R9.2, R9.6). Ambos os SKUs abaixo são elegíveis para a conta **Azure for Students** (R9.4).

### 1. Criar o App Service

```bash
RG=rg-datathon                 # mesmo resource group da storage account
PLANO=plano-datathon
APP=datathon-caged-sc-br       # precisa ser único no azurewebsites.net

az appservice plan create \
  --name "$PLANO" --resource-group "$RG" \
  --sku B1 --is-linux --location brazilsouth

az webapp create \
  --name "$APP" --resource-group "$RG" --plan "$PLANO" \
  --runtime "PYTHON:3.11"
```

> `B1` (Basic) é o menor SKU que mantém o app sempre ligado. O `F1` (Free) também funciona, mas hiberna por inatividade — o primeiro acesso depois da pausa demora, o que atrapalha uma demonstração ao vivo.

### 2. Configurar o comando de inicialização e as variáveis

O Streamlit precisa escutar na porta do App Service e em `0.0.0.0`; `startup.sh` faz isso.

```bash
az webapp config set \
  --name "$APP" --resource-group "$RG" \
  --startup-file "bash startup.sh"

az webapp config appsettings set \
  --name "$APP" --resource-group "$RG" \
  --settings \
    AZURE_STORAGE_CONNECTION_STRING="$AZURE_STORAGE_CONNECTION_STRING" \
    AZURE_BLOB_CONTAINER="$AZURE_BLOB_CONTAINER" \
    PAINEL_CHAVE_APRESENTACAO="$(python3 -c 'import secrets; print(secrets.token_urlsafe(9))')" \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true

az webapp config set --name "$APP" --resource-group "$RG" --web-sockets-enabled true
```

> O **modo apresentação** fica fora do menu e só abre em `https://<APP>.azurewebsites.net/apresentacao?chave=<PAINEL_CHAVE_APRESENTACAO>`; sem a variável, basta a URL.
>
> Use uma região próxima do público (`brazilsouth`): numa região distante, cada requisição custa ~1,5 s e o pacote do Plotly (4,7 MB, servido sem compressão pelo Streamlit) leva dezenas de segundos na primeira visita.
>
> `SCM_DO_BUILD_DURING_DEPLOYMENT=true` faz o App Service instalar o `requirements.txt` durante o deploy. As credenciais ficam nas *app settings* — variáveis de ambiente do serviço —, nunca no repositório (R8.5).
>
> `LLM_API_KEY` e `LLM_PROVIDER` **não** são configuradas aqui: o agrupamento de CBOs roda localmente durante o pipeline, fora do Azure (R5.9, R9.5). O App Service só lê tabelas agregadas.

### 3. Publicar

```bash
zip -r deploy.zip . \
  -x '.venv/*' -x '.git/*' -x 'Dados/*' -x '*__pycache__/*' \
  -x '.pytest_cache/*' -x '.hypothesis/*' -x 'data_processed/caged_bruto.parquet' \
  -x '.env' -x '*.env' -x 'notebooks/*'
unzip -l deploy.zip | grep -E '\.env$' && echo 'ERRO: .env no pacote' || echo 'ok: sem .env'

az webapp deploy \
  --name "$APP" --resource-group "$RG" \
  --src-path deploy.zip --type zip
```

O pacote inclui `.streamlit/` (tema), `data_processed/caged_agregado.parquet`, `caged_perfil.parquet`, `metadados.json` e os arquivos da IA de propósito: são o *fallback* local que mantém o painel de pé se o Blob ficar indisponível durante a apresentação (R9.6). O `.env` fica de fora — as credenciais vão nas *app settings*.

Para atualizar só os dados (sem novo deploy), envie os três artefatos ao Blob:

```bash
set -a; source .env; set +a
.venv/bin/python -c "from src.azure_upload import upload_tabelas; print(upload_tabelas(['data_processed/caged_agregado.parquet', 'data_processed/caged_perfil.parquet', 'data_processed/metadados.json'], '$AZURE_BLOB_CONTAINER'))"
```

O painel valida o schema do que leu no Blob: se a cópia estiver desatualizada (sem as colunas v2), ele usa a cópia local e diz isso na tela.

### 4. Verificar

```bash
az webapp log tail --name "$APP" --resource-group "$RG"   # acompanhar a subida
curl -sS -o /dev/null -w '%{http_code}\n' "https://$APP.azurewebsites.net"
```

O painel fica em `https://<APP>.azurewebsites.net`. A legenda abaixo do título diz se os dados vieram do `blob` ou do fallback `local` — é a forma rápida de confirmar que R9.2 está funcionando.

### Custos e limites da conta de estudante

| Recurso | SKU | Observação |
|---|---|---|
| Storage Account | Standard LRS | Poucos MB de tabelas agregadas |
| App Service Plan | B1 Linux (ou F1) | B1 não hiberna; F1 é gratuito mas pausa |
| LLM externo | API Anthropic | Fora do Azure — Azure OpenAI não é usado (R9.5) |


## Premissas documentadas

Estas premissas são relevantes para a interpretação correta dos resultados e para a auditoria do pipeline:

### (a) Exclusões já aplicadas na origem

As colunas de controle de exclusão `indicadordeexclusão` e `competênciaexc` **não estão presentes** no arquivo `Novo_Caged_MOV_Limpo.csv`. As exclusões correspondentes já foram aplicadas na origem dos dados; portanto, o pipeline parte de uma base em que esse tratamento já foi realizado e não o repete. *(R2.10, R8.3a)*

### (b) IDHM referente a 2010 e desatualizado

O indicador **IDHM utilizado é referente a 2010** e está desatualizado em relação ao período analisado (set/2025–ago/2026). Ele é anexado às tabelas agregadas como contexto socioeconômico, mas deve ser lido com essa ressalva. *(R8.3b)*

### (c) Agrupamento de CBOs roda fora do Azure

O agrupamento de códigos CBO em macrofamílias é feito por um **LLM externo (API de terceiros), executado localmente durante o pipeline — fora do Azure**. O **Azure OpenAI não é utilizado**, pois não está garantido na assinatura Azure for Students (conta de estudante). A credencial do LLM é lida da variável de ambiente `LLM_API_KEY`. *(R9.4, R9.5)*

### (d) Metodologia da classificação de CBO

Cada CBO vai ao LLM com sua descrição oficial, o nível derivado do grande grupo e a família sugerida pelo prefixo. A resposta é validada contra os conjuntos fechados (inválido → `Não classificado`) e gravada em `data_processed/cbo_macrofamilias.csv`. Uma segunda rodada, com a ordem dos códigos embaralhada, mede a concordância (log) e lista as divergências em `data_processed/cbo_divergencias.csv`.

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

### Limites da conta de estudante (Azure for Students)

A implantação opera dentro do crédito e dos limites da conta de estudante, usando apenas **SKUs elegíveis para estudante**: Azure Blob Storage padrão para as tabelas agregadas e Azure App Service em tier Free/Basic para o dashboard. Serviços que exigem Azure OpenAI são evitados. *(R9.4)*

## Credenciais e segredos

Todas as credenciais são lidas **exclusivamente de variáveis de ambiente** e **nenhum segredo é versionado no repositório** *(R8.5)*:

- `LLM_API_KEY` — credencial da API do LLM externo.
- `AZURE_STORAGE_CONNECTION_STRING` — acesso ao Azure Blob Storage e App Service.

Não há arquivos de credenciais commitados; defina as variáveis no ambiente de execução (shell, arquivo `.env` não versionado, ou nas configurações do App Service). O código interrompe a etapa correspondente quando a variável está ausente ou vazia, sem registrar os valores em arquivos do repositório.

## Estrutura do projeto

```
DataThon/
├── Dados/                          # fontes originais
├── notebooks/
│   └── 01_pipeline.ipynb           # orquestra o pipeline ponta a ponta
├── scripts/
│   └── baixar_malha_sc.py          # baixa a malha municipal de SC (IBGE)
├── src/
│   ├── ingestao.py                 # Ingestor
│   ├── limpeza.py                  # Limpador
│   ├── mapeamentos.py              # tabelas de domínio do dicionário
│   ├── enriquecimento.py           # Junta_Relacional
│   ├── cbo_ia.py                   # Classificador_de_CBO (LLM externo)
│   ├── metricas.py                 # Calculador_de_Metricas
│   ├── agregador.py                # Agregador
│   └── azure_upload.py             # upload Blob Storage
├── data_processed/                 # artefatos gerados pelo pipeline
├── dashboard/
│   ├── app.py                      # Streamlit
│   └── geo/sc_municipios.geojson   # malha para o mapa coroplético
├── tests/                          # testes unitários e property-based
├── requirements.txt                # versões exatas fixadas
├── startup.sh                      # comando de inicialização no Azure App Service
├── .env.example                    # modelo das variáveis de ambiente
└── README.md
```

## Testes

```bash
pytest
```

Os testes combinam testes de exemplo (`pytest`) e testes de propriedade (`hypothesis`, mínimo de 100 exemplos por propriedade). LLM e Azure são sempre mockados nos testes para isolar a lógica e evitar custo/rede.

`tests/test_contrato_dados_reais.py` é a exceção útil: lê apenas o cabeçalho e as primeiras linhas dos arquivos em `Dados/` e afirma as premissas de formato das quais o Limpador depende — vírgula decimal no CAGED, ponto decimal nos indicadores do IBGE, `tamestabjan` como código de faixa. Fixtures descrevem o formato que se *acredita* ter; esse teste verifica o que o arquivo *tem*. Ele é pulado automaticamente quando os dados não estão presentes.
