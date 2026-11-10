# Requirements Document

## Introduction

Este documento define os requisitos para o pipeline de dados e dashboard analítico do Datathon CDIA 2026 — "Raio-X do Mercado de Trabalho e Vagas Industriais em Santa Catarina". A solução atua como consultoria de dados que responde à pergunta central de negócio: *"Quais regiões e setores industriais de Santa Catarina estão enfrentando apagão de mão de obra ou expansão acelerada, e como os indicadores de renda e escolaridade explicam esses gargalos?"*

O escopo cobre o pipeline completo (ingestão → limpeza → cruzamento relacional → métricas de negócio → enriquecimento de CBOs via IA → agregações) e um dashboard interativo com no mínimo 3 KPIs, além dos requisitos de reprodutibilidade e documentação exigidos pelo desafio. As fontes de dados são o CAGED movimentado de SC (~3,4 milhões de linhas), a tabela de municípios de SC (295 municípios — a 296ª linha do arquivo é um rodapé de notas/fontes do IBGE, descartado pela junção) e o dicionário de dados.

## Glossary

- **Pipeline**: Conjunto de etapas automatizadas que transformam os dados brutos em bases agregadas prontas para consumo pelo dashboard.
- **Ingestor**: Componente responsável pela carga e validação de schema dos arquivos de origem.
- **Limpador**: Componente responsável pelo tratamento de tipos, valores ausentes e decodificação de domínios.
- **Junta_Relacional**: Componente responsável por cruzar a base CAGED com a base de municípios.
- **Calculador_de_Metricas**: Componente responsável por calcular as métricas de negócio.
- **Classificador_de_CBO**: Componente responsável por agrupar códigos CBO em macrofamílias usando um modelo de linguagem (LLM).
- **Agregador**: Componente responsável por gerar tabelas agregadas por recortes (região, setor, macrofamília, mês).
- **Dashboard**: Aplicação interativa em Streamlit/Plotly que apresenta KPIs e visualizações.
- **CAGED**: Arquivo `Novo_Caged_MOV_Limpo.csv` contendo movimentações de emprego de Santa Catarina.
- **Base_de_Municipios**: Arquivo `Municipios_SC_limpo.csv` contendo indicadores socioeconômicos dos 295 municípios de SC (mais uma linha final de notas/fontes do IBGE, sem código válido, excluída da junção por R3.6).
- **Dicionario_de_Dados**: Arquivo `Dicionario_de_dados.xlsx` que define os domínios das variáveis categóricas.
- **Saldo_Liquido**: Soma algébrica da coluna `saldomovimentação` (+1 admissão, -1 desligamento) para um recorte.
- **Saldo_por_10k**: Saldo líquido normalizado por 10.000 habitantes da população estimada 2026.
- **Turnover**: Rotatividade estimada como min(admissões, desligamentos) sobre max(admissões, desligamentos) do recorte, usada como proxy de apagão de mão de obra. Vale 1 quando admissões e desligamentos se equilibram (rotatividade pura, saldo nulo) e 0 quando há só entrada ou só saída (crescimento ou encolhimento puro).
- **estoque base**: *(conceito abandonado — ver Turnover.)* A redação original definia o denominador do Turnover como o estoque de vínculos ativos, representado pela coluna `tamestabjan`. Duas correções de premissa se acumularam: (a) `tamestabjan` **não** é contagem de vínculos e sim o **código da faixa de tamanho** do estabelecimento em janeiro (1 = "Zero", 5 = "De 20 a 49", 10 = "1000 ou Mais", conforme o Dicionario_de_Dados); e (b) o estoque de um recorte **não é recuperável** do CAGED movimentado, que não traz identificador de estabelecimento — um estabelecimento com 50 movimentações aparece 50 vezes e não há como saber que é o mesmo. Medido sobre os dados reais, usar a faixa média saturava 62,7% dos recortes no teto de 1,0 e somá-la por linha derrubava a mediana para 0,035. O denominador passou a ser `max(admissões, desligamentos)`, que é identificável e, sob o modelo de que o volume de movimentação é proporcional ao tamanho do estabelecimento, equivale à fórmula com estoque a menos de uma constante.
- **Indice_de_Aquecimento**: Métrica composta que combina saldo relativo e crescimento mensal para distinguir expansão acelerada de apagão.
- **Macrofamilia_CBO**: Agrupamento de alto nível de ocupações (ex.: Engenharia/Técnico, Operacional de Produção, Administrativo, Logística, TI).
- **Chave_Municipal**: Identificador de município de 6 dígitos usado como chave comum entre CAGED e Base_de_Municipios.
- **Secao_Industrial**: Seções CNAE 2.0 B, C, D, E e F, com foco principal em C (indústria de transformação).
- **KPI**: Indicador-chave de desempenho exibido no Dashboard.
- **Parquet**: Formato de arquivo colunar usado para persistir dados processados.
- **LLM_Externo**: Serviço de modelo de linguagem de terceiros (ex.: OpenAI, Google Gemini, Anthropic) acessado via API, executado localmente durante o pipeline (não hospedado no Azure).
- **Blob_Storage**: Contêiner de Azure Storage Account onde as tabelas agregadas são armazenadas.
- **App_Service**: Serviço do Azure App Service que hospeda a aplicação do Dashboard.
- **Conta_Azure_Estudante**: Assinatura Azure for Students, com crédito limitado e sem acesso garantido ao Azure OpenAI.

## Requirements

### Requirement 1: Ingestão e validação dos dados de origem

**User Story:** Como engenheiro de dados, quero carregar e validar os arquivos de origem, para que o pipeline parta de uma base estruturada e confiável.

#### Acceptance Criteria

1. WHEN o arquivo CAGED é carregado, THE Ingestor SHALL ler o arquivo usando separador `;` e decimal `,`.
2. WHEN a Base_de_Municipios é carregada, THE Ingestor SHALL ler o arquivo usando separador `,`.
3. WHEN o arquivo CAGED é carregado, THE Ingestor SHALL descartar as colunas `Unnamed: 0.1` e `Unnamed: 0`.
4. WHEN o arquivo CAGED é carregado, THE Ingestor SHALL verificar que a coluna `uf` contém exclusivamente o valor `42`.
5. IF a coluna `uf` contém pelo menos 1 registro com valor diferente de `42`, THEN THE Ingestor SHALL registrar um erro identificando a quantidade de registros divergentes e interromper o processamento sem persistir.
6. WHEN a carga do CAGED é concluída, THE Ingestor SHALL verificar a presença das colunas `competênciamov`, `município`, `seção`, `subclasse`, `saldomovimentação`, `cbo2002ocupação`, `graudeinstrução`, `idade`, `raçacor`, `sexo`, `salário` e `valorsaláriofixo`.
7. IF 1 ou mais colunas esperadas estão ausentes no CAGED, THEN THE Ingestor SHALL registrar um erro identificando cada coluna ausente pelo nome e interromper o processamento sem persistir.
8. WHEN a carga inicial do CAGED é concluída sem erros de validação, THE Ingestor SHALL persistir o conteúdo carregado em formato Parquet.
9. THE Ingestor SHALL registrar a contagem exata de linhas lidas de cada arquivo de origem.
10. IF um arquivo de origem está ausente, inacessível ou ilegível, THEN THE Ingestor SHALL registrar um erro identificando o arquivo e interromper o processamento sem persistir.

### Requirement 2: Limpeza, conversão de tipos e decodificação de domínios

**User Story:** Como engenheiro de dados, quero tratar tipos, valores ausentes e códigos de domínio, para que as análises usem dados consistentes e legíveis.

#### Acceptance Criteria

1. WHEN as colunas `salário` e `valorsaláriofixo` são processadas, THE Limpador SHALL converter cada valor do formato brasileiro (vírgula como separador decimal, ex.: `2018,00`) para número de ponto flutuante com precisão de 2 casas decimais.
2. IF um valor das colunas `salário` ou `valorsaláriofixo` não puder ser convertido para número de ponto flutuante, THEN THE Limpador SHALL substituir o valor por um marcador de ausência (NaN) e registrar a coluna, a competência e a quantidade de valores não convertidos.
3. WHEN os indicadores numéricos da Base_de_Municipios são processados, THE Limpador SHALL converter cada valor para número de ponto flutuante usando **ponto como separador decimal**, que é o formato do arquivo exportado do IBGE (ex.: `0.694`, `44644.04`). *(Correção de premissa: a redação original dizia "formato brasileiro"; aplicar a conversão BR a este arquivo destrói o separador decimal, transformando `0.694` em `694.0`. O formato brasileiro vale para as colunas monetárias do CAGED, tratadas por R2.1.)*
4. WHEN um valor igual a `-` é encontrado na Base_de_Municipios, THE Limpador SHALL substituir o valor por um marcador de ausência (NaN).
5. WHEN as colunas categóricas `graudeinstrução`, `raçacor`, `sexo`, `tipomovimentação`, `categoria`, `tamestabjan`, `unidadesaláriocódigo` e `seção` são processadas, THE Limpador SHALL substituir cada código pelo rótulo legível definido no Dicionario_de_Dados.
6. IF um código categórico não possui rótulo correspondente no Dicionario_de_Dados, THEN THE Limpador SHALL preservar o valor original e registrar o nome da coluna, o código não mapeado e a quantidade de ocorrências não mapeadas.
7. WHEN uma célula de coluna categórica está vazia ou ausente, THE Limpador SHALL substituir o valor por um marcador de ausência (NaN) sem interromper o processamento das demais linhas.
8. WHEN a coluna `competênciamov` (formato AAAAMM) é processada, THE Limpador SHALL manter apenas os registros cuja competência esteja no intervalo de 202509 (setembro de 2025) a 202608 (agosto de 2026), inclusive os limites.
9. IF um registro possui competência fora do intervalo de 202509 a 202608, THEN THE Limpador SHALL excluir o registro e registrar a quantidade total de registros excluídos pelo filtro de competência.
10. THE Limpador SHALL documentar que as exclusões (colunas `indicadordeexclusão` e `competênciaexc`) já foram aplicadas na origem e não estão presentes no arquivo.

### Requirement 3: Cruzamento relacional entre CAGED e municípios

**User Story:** Como analista de dados, quero cruzar as movimentações do CAGED com os indicadores municipais, para que as métricas possam ser contextualizadas por características socioeconômicas.

#### Acceptance Criteria

1. WHEN a Chave_Municipal é gerada a partir do CAGED, THE Junta_Relacional SHALL usar o código de município com exatamente 6 dígitos numéricos.
2. WHEN a Chave_Municipal é gerada a partir da Base_de_Municipios, THE Junta_Relacional SHALL usar os 6 primeiros dígitos do código IBGE de 7 dígitos numéricos.
3. WHEN as duas bases são cruzadas, THE Junta_Relacional SHALL preservar todos os registros do CAGED (junção à esquerda), atribuindo valores ausentes aos indicadores municipais quando não houver correspondência.
4. WHEN o cruzamento é concluído, THE Junta_Relacional SHALL registrar a quantidade de registros do CAGED sem município correspondente, o total de registros lidos do CAGED e o total com chave municipal válida.
5. IF a proporção de registros do CAGED sem correspondência excede 1% do total de registros do CAGED, THEN THE Junta_Relacional SHALL registrar um alerta listando os códigos municipais não correspondidos e a contagem por código.
6. IF um código municipal é malformado (comprimento diferente do esperado ou não numérico) em qualquer das bases, THEN THE Junta_Relacional SHALL excluir o registro da junção e registrar a contagem de registros excluídos por base.

### Requirement 4: Cálculo das métricas de negócio

**User Story:** Como consultor de dados, quero calcular as métricas de mercado de trabalho, para que seja possível diagnosticar apagão e expansão por região e setor.

#### Acceptance Criteria

1. THE Calculador_de_Metricas SHALL calcular o Saldo_Liquido como a soma de `saldomovimentação` por recorte de município, Secao_Industrial e mês, onde admissões correspondem a `saldomovimentação` igual a +1 e desligamentos a -1.
2. WHEN a população estimada 2026 de um município é um número maior que zero, THE Calculador_de_Metricas SHALL calcular o Saldo_por_10k como o Saldo_Liquido dividido pela população estimada 2026 multiplicado por 10.000.
3. IF a população estimada 2026 de um município está ausente ou é zero, THEN THE Calculador_de_Metricas SHALL marcar o Saldo_por_10k como ausente para esse município.
4. THE Calculador_de_Metricas SHALL calcular o Turnover por recorte de município e Secao_Industrial no período set/2025–ago/2026 como o mínimo entre o total de admissões e o total de desligamentos dividido pelo **máximo** entre esses dois totais, resultando por construção no intervalo de 0 a 1. *(Correção de premissa: ver "estoque base" no Glossary — o estoque não é recuperável desta base.)*
5. IF um recorte não possui nenhuma admissão nem desligamento, THEN THE Calculador_de_Metricas SHALL marcar o Turnover como ausente para esse recorte (não há rotatividade definida sobre o conjunto vazio).
6. THE Calculador_de_Metricas SHALL calcular o salário médio de admissão e o salário médio de desligamento por Secao_Industrial como a média aritmética da coluna `salário` (em R$, 2 casas decimais), excluindo da média os valores ausentes.
7. THE Calculador_de_Metricas SHALL calcular a distribuição de grau de instrução dos admitidos e dos desligados por Secao_Industrial.
8. THE Calculador_de_Metricas SHALL calcular o Indice_de_Aquecimento por recorte como a soma entre o Saldo_por_10k e a variação do Saldo_Liquido em relação ao mês imediatamente anterior.
9. IF um recorte não possui mês anterior no período, THEN THE Calculador_de_Metricas SHALL atribuir valor zero à componente de variação do Indice_de_Aquecimento.
10. IF um recorte não possui admissões nem desligamentos no período, THEN THE Calculador_de_Metricas SHALL atribuir valor zero ao Saldo_Liquido desse recorte.

### Requirement 5: Enriquecimento de CBOs com agrupamento via IA

**User Story:** Como analista de qualificação, quero agrupar centenas de ocupações em macrofamílias usando IA, para que o diagnóstico de qualificação seja interpretável por setor.

#### Acceptance Criteria

1. WHEN o conjunto de CBOs é preparado, THE Classificador_de_CBO SHALL extrair a lista de códigos `cbo2002ocupação` distintos presentes no CAGED, descartando valores nulos ou vazios.
2. WHEN a lista de CBOs é enviada ao LLM_Externo, THE Classificador_de_CBO SHALL solicitar o agrupamento de cada código em exatamente uma Macrofamilia_CBO pertencente a um conjunto pré-definido de 5 a 12 macrofamílias.
3. WHILE houver mais de 100 códigos CBO a classificar, THE Classificador_de_CBO SHALL enviar as requisições ao LLM_Externo em lotes de no máximo 100 códigos por requisição.
4. THE Classificador_de_CBO SHALL persistir o mapeamento de código CBO para Macrofamilia_CBO em um arquivo CSV, garantindo que cada código distinto apareça exatamente uma vez.
5. WHEN o mapeamento é concluído, THE Classificador_de_CBO SHALL combinar a Macrofamilia_CBO à base cruzada pelo código `cbo2002ocupação` e registrar a contagem de códigos sem correspondência.
6. IF um código CBO não recebe uma Macrofamilia_CBO do LLM_Externo, ou recebe uma Macrofamilia_CBO fora do conjunto pré-definido, THEN THE Classificador_de_CBO SHALL atribuir a Macrofamilia_CBO `Não classificado` ao código.
7. IF uma requisição ao LLM_Externo falhar ou não responder em até 60 segundos, THEN THE Classificador_de_CBO SHALL repetir a requisição em até 3 tentativas e, esgotadas as tentativas, atribuir a Macrofamilia_CBO `Não classificado` aos códigos do lote e registrar uma indicação de falha.
8. THE Classificador_de_CBO SHALL registrar o prompt utilizado no agrupamento junto ao mapeamento gerado.
9. THE Classificador_de_CBO SHALL executar o agrupamento localmente durante o Pipeline, usando o LLM_Externo via API, sem depender de Azure OpenAI nem de qualquer serviço de IA hospedado no Azure.

### Requirement 6: Geração das agregações para o dashboard

**User Story:** Como desenvolvedor do dashboard, quero bases agregadas e otimizadas, para que o dashboard carregue e filtre dados com desempenho adequado.

#### Acceptance Criteria

1. THE Agregador SHALL gerar tabelas agregadas com uma linha por combinação distinta de região, Secao_Industrial, Macrofamilia_CBO e mês.
2. WHERE uma combinação de recorte não possui registros no CAGED, THE Agregador SHALL omitir essa combinação das tabelas agregadas.
3. WHEN as agregações são concluídas, THE Agregador SHALL exportar as tabelas agregadas em formato Parquet ou CSV.
4. IF a exportação das tabelas agregadas falhar, THEN THE Agregador SHALL registrar um erro indicando o arquivo de destino e preservar o estado sem gravar arquivo parcial.
5. THE Agregador SHALL incluir nas tabelas agregadas o Saldo_Liquido, o Saldo_por_10k, o Turnover, o Indice_de_Aquecimento, o salário médio de admissão, o salário médio de desligamento e a escolaridade média dos admitidos, com valores numéricos arredondados a 2 casas decimais.
6. THE Agregador SHALL associar a cada recorte municipal os indicadores de população estimada 2026, IDHM 2010 e PIB per capita 2023.
7. WHERE um indicador municipal está ausente para um município, THE Agregador SHALL registrar o valor como ausente (NaN) sem interromper a agregação.

### Requirement 7: Dashboard interativo com no mínimo três KPIs

**User Story:** Como tomador de decisão da indústria, quero um dashboard interativo com indicadores claros, para que eu localize gargalos, entenda a causa raiz e decida ações.

#### Acceptance Criteria

1. WHEN o Dashboard é carregado, THE Dashboard SHALL apresentar no mínimo 3 KPIs derivados das métricas de negócio, cada um exibindo rótulo e valor numérico.
2. WHEN o Dashboard é carregado, THE Dashboard SHALL apresentar um mapa coroplético de Santa Catarina colorindo cada município pelo Saldo_por_10k, com escala de cores divergente em que valores negativos e positivos são visualmente distinguíveis e com legenda indicando os limites mínimo e máximo da escala.
3. WHEN o Dashboard é carregado, THE Dashboard SHALL apresentar um ranking de Secao_Industrial ordenado de forma decrescente por Saldo_Liquido, exibindo para cada seção os valores de Saldo_Liquido e Turnover.
4. WHEN o Dashboard é carregado, THE Dashboard SHALL apresentar uma visualização que relaciona o salário médio de admissão e o grau de instrução — representado pelo nível ordinal médio dos admitidos, de modo a permitir um eixo contínuo —, segmentada por Secao_Industrial ou Macrofamilia_CBO.
5. WHEN o usuário aplica um filtro de período, região, Secao_Industrial ou Macrofamilia_CBO, THE Dashboard SHALL atualizar os KPIs e todas as visualizações para refletir apenas os registros correspondentes ao filtro selecionado.
6. IF o filtro selecionado não corresponde a nenhum registro, THEN THE Dashboard SHALL exibir cada KPI com valor zero e apresentar em cada visualização uma indicação de ausência de dados, sem encerrar a aplicação.
7. WHEN o Dashboard é iniciado, THE Dashboard SHALL carregar os dados a partir das tabelas agregadas geradas pelo Agregador.
8. IF as tabelas agregadas geradas pelo Agregador estão ausentes ou não podem ser lidas, THEN THE Dashboard SHALL exibir uma mensagem indicando a indisponibilidade dos dados e SHALL abster-se de renderizar os KPIs e as visualizações.

### Requirement 8: Reprodutibilidade e documentação do pipeline

**User Story:** Como avaliador do datathon, quero reproduzir o pipeline de ponta a ponta, para que eu possa auditar o tratamento, as premissas e os resultados.

#### Acceptance Criteria

1. WHEN o notebook ou script do pipeline é executado a partir dos arquivos de dados de origem, THE Pipeline SHALL executar em sequência as etapas de carga, tratamento, exclusões, enriquecimento por IA e exportação sem exigir intervenção manual entre etapas, produzindo os arquivos de saída consumidos pelo dashboard.
2. THE Pipeline SHALL disponibilizar um arquivo de dependências que declara todas as bibliotecas necessárias para executar o pipeline, cada uma com versão exata fixada (sem faixas de versão).
3. THE Pipeline SHALL disponibilizar documentação textual que registra, no mínimo, duas premissas: (a) que as exclusões já foram aplicadas na origem dos dados e (b) que o indicador IDHM é referente a 2010 e está desatualizado.
4. WHEN qualquer uma das etapas de carga, tratamento, exclusões, enriquecimento por IA ou exportação é iniciada, THE Pipeline SHALL registrar uma mensagem de progresso que identifica, de forma única, a etapa em execução.
5. THE Pipeline SHALL ler duas credenciais distintas exclusivamente de variáveis de ambiente, sem registrar os valores em arquivos versionados no repositório: (a) a credencial de API do LLM_Externo e (b) as credenciais de acesso ao Azure (Blob_Storage e App_Service).
6. IF o enriquecimento via IA requer a credencial do LLM_Externo e a variável de ambiente correspondente está ausente ou vazia, THEN THE Pipeline SHALL interromper a execução antes de chamar a API externa e exibir uma mensagem de erro indicando que a credencial do LLM_Externo não foi fornecida.
7. IF o upload das tabelas agregadas para o Blob_Storage requer a credencial de acesso ao Azure e a variável de ambiente correspondente está ausente ou vazia, THEN THE Pipeline SHALL interromper a etapa de upload antes de chamar o Azure e exibir uma mensagem de erro indicando que a credencial de acesso ao Azure não foi fornecida.
8. THE Pipeline SHALL disponibilizar um arquivo README que descreve, no mínimo: os pré-requisitos de ambiente, os comandos para instalar as dependências, os comandos para executar o pipeline e os comandos para iniciar o dashboard.

### Requirement 9: Implantação no Azure com conta de estudante

**User Story:** Como responsável pela implantação, quero hospedar os dados agregados e o dashboard no Azure dentro dos limites de uma conta de estudante, para que a solução seja demonstrável publicamente sem custos adicionais e sem depender de serviços indisponíveis.

#### Acceptance Criteria

1. WHEN a etapa de agregação é concluída, THE Pipeline SHALL enviar (upload) as tabelas agregadas geradas pelo Agregador para o Blob_Storage.
2. WHILE o Dashboard está hospedado no App_Service, THE Dashboard SHALL ler as tabelas agregadas a partir do Blob_Storage.
3. IF as credenciais de acesso ao Azure estão ausentes ou inválidas no momento do upload, THEN THE Pipeline SHALL registrar um erro e abster-se de enviar dados parciais ao Blob_Storage.
4. THE Pipeline SHALL operar dentro dos limites e do crédito da Conta_Azure_Estudante, utilizando SKUs elegíveis para estudante e evitando serviços que exijam Azure OpenAI.
5. THE Pipeline SHALL documentar que o agrupamento de CBOs via LLM_Externo é executado fora do Azure, dado que o Azure OpenAI não está disponível na Conta_Azure_Estudante (premissa).
6. WHERE o Blob_Storage não está acessível, THE Dashboard SHALL permitir a leitura das tabelas agregadas a partir de uma cópia local como alternativa (fallback), para não bloquear demonstrações.
