# Raio-X da Indústria SC

**Apagão de mão de obra e expansão acelerada na indústria catarinense, a partir dos microdados do Novo CAGED.**
Datathon CDIA 2026 — UniSENAI/SENAI, Santa Catarina.

| | |
|---|---|
| **Painel interativo** | **https://datathon-caged-sc-br.azurewebsites.net/** |
| **Slides do pitch** | [`docs/Pitch_Executivo_Industria_SC.pdf`](docs/Pitch_Executivo_Industria_SC.pdf) |
| **Pipeline completo** | [`notebooks/01_pipeline.ipynb`](notebooks/01_pipeline.ipynb) |

> O painel roda no plano gratuito do Azure e hiberna sem uso: o primeiro acesso depois de uma pausa pode levar cerca de 1 minuto.

---

## A pergunta e a resposta

> *"Quais regiões e setores industriais de Santa Catarina estão enfrentando apagão de mão de obra ou expansão acelerada, e como os indicadores de renda e escolaridade explicam esses gargalos?"*

**O apagão da indústria catarinense é de retenção, não de contratação.** A indústria contrata muito e cresce pouco: troca a equipe no mesmo ritmo do Brasil, mas aqui muito mais gente pede para sair. A renda explica só em parte, e a escolaridade não explica.

Números da indústria de transformação de SC, set/25–ago/26 (o recorte em que o painel abre):

| | |
|---|---|
| Movimentações | **835.950** (418.511 contratações e 417.439 desligamentos) |
| Saldo líquido | **+1.072 vagas** (0,1%) |
| Desligamentos a pedido do trabalhador | **50,9%** (Brasil: 37,3%) |
| Rotatividade | **27,4%** (Brasil: 27,6%) |

Os slides usam o recorte mais amplo, **Indústria (B–F)**, que inclui extrativa, energia, saneamento e construção (1,14 milhão de movimentações, +2.726 vagas, 47,7% a pedido). No painel, a troca é feita no filtro **Escopo**.

## O que encontramos

### 1. Onde está o problema

Cada combinação de mesorregião e setor (63 grupos com dados suficientes) foi posicionada numa matriz de **dinamismo** (o grupo cresce?) × **tensão** (o grupo perde a equipe?):

| Quadrante | Grupos | Exemplos |
|---|---|---|
| **Apagão: cresce, mas não retém** | 13 | Alimentos e bebidas no Sul (saldo +891) e no Norte (+313); metalurgia no Sul troca 45% da equipe por ano, e 73% de quem sai tem menos de 1 ano de casa |
| **Expansão acelerada** | 14 | Autopeças no Vale do Itajaí (+1.602, +20,7% no ano), mas 95% do saldo vem de Navegantes e 43% de um único mês: parece projeto, não tendência |
| Retração com rotatividade | 20 | |
| Estagnação | 16 | |

A demanda existe: os grupos em Apagão contratam 66 pessoas para cada 100 empregos (mediana), contra 56 no estado.

### 2. Por que acontece

- **Renda explica em parte.** Comparando dentro da mesma ocupação, quem entra ganha 96% do salário de quem sai. Onde a entrada paga relativamente menos, mais gente pede para sair (correlação de −0,39).
- **Escolaridade não explica.** Quem entra tem, em média, quase a mesma escolaridade de quem sai (−0,08 nível). A exceção é Alimentos e bebidas no Oeste (−0,95 nível). Na linha de produção, o diploma superior paga só 3% a mais na entrada.
- **Trocar a equipe é do Brasil; pedir para sair é de SC.** A rotatividade da transformação é igual à nacional, mas a saída a pedido é 13,6 pontos maior (intervalo de confiança de SC: 49,4% a 52,8%).

### 3. O que fazer

As três ações de maior impacto, cada uma ligada a uma macrofamília de ocupações agrupada por IA:

| | Ação | Onde | Quem age e prazo | Meta em 12 meses |
|---|---|---|---|---|
| 1 | **Retenção não salarial** | Operação de linha e processo, Oeste | Empresa, 0–3 meses | saída a pedido de 59,0% para 55,0% |
| 2 | **Formação direcionada** | Magarefe, trabalhador de laticínios e desossador, Oeste | Federação–SENAI, 3–12 meses | diferença de escolaridade de −0,95 para −0,51 |
| 3 | **Atração de talentos** | Metalmecânica e eletroeletrônica (nível Qualificado), do Sul para o Vale do Itajaí | Empresa + poder público, 3–12 meses | desligamento precoce de 67,2% para 66,5% |

Só no grupo da ação 1, repor quem pede para sair custa cerca de **R$ 118 milhões por ano** (premissa do time: 3 salários por reposição; o painel tem um simulador para ajustar).

## Como chegamos aqui

1. **Dados.** Novo CAGED de SC com **24 meses** (set/24–ago/26), reconstruído do FTP do MTE com as declarações fora do prazo e as exclusões (MOV + FOR − EXC). No mesmo período, confere com a base fornecida pela organização (+0,02% nas admissões e +0,005% nos desligamentos). Estoque de vínculos da **RAIS 2025** (2,57 milhões) para a rotatividade e o desligamento precoce. População, IDHM e PIB dos municípios para o saldo por 10 mil habitantes. Salários deflacionados pelo INPC.
2. **IA nas ocupações.** As **2.206 CBOs** foram agrupadas em 11 macrofamílias e 4 níveis de qualificação por um LLM, com regras explícitas e justificativa obrigatória quando a IA foge da hierarquia da CBO. Uma segunda classificação, feita por outro modelo, serviu de auditoria: 91,4% de concordância na família e 92,2% no nível. O ganho principal da IA é o nível de qualificação, ajustado em 34,6% das movimentações. Prompts, respostas e revisões manuais estão em [`ia_cbo/`](ia_cbo/).
3. **Indicadores.** Tensão = rotatividade descontada, saída voluntária e desligamento precoce; dinamismo = variação do emprego e aceleração entre os dois blocos de 12 meses. Toda taxa exige pelo menos 100 movimentações no grupo.
4. **Painel.** Streamlit no Azure App Service, com os dados agregados no Azure Blob Storage. Sete páginas, na ordem da narrativa: **Panorama** → **Quem precisa de atenção** → **Por que acontece** → **Que profissional falta** → **O que fazer** → **Ficha do território** → **Metodologia**. Todo número é recalculado a partir dos filtros.
5. **Qualidade.** 411 testes automatizados (pytest + Hypothesis) cobrem o pipeline, as métricas, as regras e as páginas.

## Premissas e limites

- **O CAGED mede movimentações, não vagas abertas.** O apagão é inferido por sinais de tensão, não observado diretamente; a demanda é aproximada pela taxa de admissão.
- **Só emprego formal (CLT).** Informalidade, autônomos e PJ ficam de fora.
- **Os salários são declarados pelo empregador.** O IDHM é de 2010.
- **A classificação da IA é uma interpretação**, mitigada por regras fechadas e auditada contra outro modelo.
- **A construção civil tem rotatividade estrutural de obra** (59,7%) e aparece separada, para não dominar o ranking de tensão.

A lista completa está na página **Metodologia** do painel. O que não coube está em [`docs/ROADMAP.md`](docs/ROADMAP.md).

## O que tem neste repositório

| Pasta | Conteúdo |
|---|---|
| [`notebooks/`](notebooks/) | `01_pipeline.ipynb`: o pipeline de ponta a ponta, executado e com as saídas |
| [`src/`](src/) | código do pipeline (ingestão, exclusões, cruzamentos, métricas, IA, agregação, upload) |
| [`ia_cbo/`](ia_cbo/) | prompts, respostas da IA, revisão manual e script para repetir a classificação pela API |
| [`dashboard/`](dashboard/) | o painel em Streamlit |
| [`data_processed/`](data_processed/) | tabelas agregadas que o painel lê, com `metadados.json` (commit e impressão digital de cada arquivo) |
| [`tests/`](tests/) | os 411 testes automatizados |
| [`docs/`](docs/) | slides, roteiro do pitch, registro das correções ([`CHANGELOG_BANCA.md`](docs/CHANGELOG_BANCA.md)) e [como rodar tudo do zero](docs/COMO_RODAR.md) |

## Equipe

Luca Jahn · Gabriel Sartori · Pedro Zanette · João Benvenutti · João Silva
