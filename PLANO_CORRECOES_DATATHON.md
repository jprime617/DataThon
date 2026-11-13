# Plano de correção e melhorias — Raio-X da Indústria SC (Datathon CDIA 2026)

> **Como usar:** coloque este arquivo na raiz do repositório e diga ao Claude Code:
> `Leia PLANO_CORRECOES_DATATHON.md e execute o plano na ordem de prioridade, seguindo as regras de trabalho da seção 1.`

---

## 0. Contexto (leia antes de tocar no código)

Você está corrigindo o painel **Raio-X da Indústria SC**, em produção em
`https://datathon-caged-sc-br.azurewebsites.net/`. Ele é feito em Streamlit, roda no Azure App Service e lê tabelas pré-agregadas do Azure Blob Storage, com cópia local como reserva. O pipeline fica em `notebooks/01_pipeline.ipynb` e a classificação de CBO por IA, em `ia_cbo/`.

O projeto concorre no **Datathon "Raio-X do Mercado de Trabalho e Vagas Industriais em SC"** (UniSENAI). A **pergunta central** é:

> "Quais regiões e setores industriais de SC estão enfrentando **apagão de mão de obra** ou **expansão acelerada**, e como os indicadores de **renda e escolaridade** explicam esses gargalos?"

A banca é formada por especialistas de empresas parceiras e avalia **5 critérios**:
1. Compreensão do problema e do contexto industrial.
2. Embasamento analítico e diagnóstico, incluindo premissas e limites.
3. Dashboard e storytelling: KPIs em destaque, gráficos adequados, narrativa fluida.
4. Recomendações e valor de negócio, com ligação lógica com as macrofamílias de CBO geradas por IA.
5. Pitch de 3 minutos.

Pelo guia, o diretor que abre o painel precisa conseguir **(1) localizar o problema, (2) entender a causa raiz e (3) tomar uma decisão**. O guia define:
- **Apagão:** alta demanda por trabalhadores, com escassez de qualificados **ou** forte rotatividade.
- **Expansão acelerada:** saldo vertiginoso de vagas, que pressiona qualificação e faixas salariais.

Os exemplos de recomendação citados no guia são: **formação profissional direcionada**, **revisão de faixas salariais** e **incentivos para atrair talentos regionais**.

**Prazo:** os pitches são em **13/11/2026, às 10h30**. Tudo que for **P0** precisa estar em produção antes disso. **P1** entra só se o P0 estiver fechado e testado. **P2** fica para depois do datathon: não implemente; registre em `docs/ROADMAP.md`.

---

## 1. Regras de trabalho

1. **Explore antes de editar.** Mapeie a estrutura do repositório, as páginas do Streamlit, onde os indicadores são calculados (pipeline × painel), onde ficam os rótulos e textos, e quais testes existem. Escreva um resumo curto em `docs/MAPA_DO_CODIGO.md` antes da primeira alteração.
2. **Um item por commit**, com o ID do item na mensagem (ex.: `BUG-01: ...`). Crie uma branch `fix/banca` a partir da principal.
3. **Não invente números nem fatos.** Todo texto do painel com número deve ser calculado a partir dos dados, não escrito à mão. Fatos externos (ex.: estaleiros) só entram com a fonte citada na tela.
4. **Verifique as hipóteses nos dados.** Vários itens deste plano são hipóteses levantadas olhando só o painel publicado. Se a investigação mostrar que a hipótese está errada, **não force a correção**: registre o que encontrou no relatório final e siga em frente.
5. **Centralize rótulos e regras.** Nomes de quadrantes, causas, alavancas e limiares devem morar num único módulo de constantes ou config, para que mudar um nome não deixe a tela inconsistente.
6. **Testes:** rode a suíte existente depois de cada item. Toda regra nova ou alterada (limiar, classificação, formatação) ganha teste unitário.
7. **Verificação visual:** depois de cada item que mexe em tela, rode `streamlit run` localmente e confira a página afetada, com e sem filtros (inclusive um recorte vazio).
8. **Pipeline × painel:** prefira corrigir na camada do painel quando o dado agregado já existir. Só reprocesse o pipeline quando for indispensável. Se reprocessar, regenere os agregados, publique no Blob e confirme o novo `commit do pipeline` na página Metodologia.
9. **Não rode o LLM de novo** para reclassificar as 2.206 CBOs antes do pitch. Correções pontuais de classificação entram por um arquivo de overrides (ver TAX-03).
10. **Mantenha um `docs/CHANGELOG_BANCA.md`** com um registro por item: o que mudou, onde, e **os números de antes e depois** de todo indicador que aparece no pitch. O time precisa disso para atualizar a fala.

---

## 2. Backlog priorizado

Legenda: **P0** = antes do pitch · **P1** = se sobrar tempo · **P2** = só no roadmap.
Cada item traz o **problema**, a **evidência** (o que se vê hoje no painel), **o que alterar** e o **critério de aceite**.

---

### ÉPICO A — Bugs de cálculo e de dados (P0)

#### BUG-01 · Comparação "vs estado" sem sentido em métricas absolutas — P0
- **Problema:** na Ficha do território, o cartão "Saldo" mostra a diferença entre o saldo absoluto da região e o saldo absoluto do estado inteiro.
- **Evidência:** Grande Florianópolis mostra "Saldo −1.913 · −4.639 vs estado" (−1.913 − 2.726). Com o setor Veículos filtrado, a microrregião de Araranguá mostra "Saldo 0 · −1.887 vs estado".
- **Alterar:** em métricas **absolutas** (saldo, movimentações, admissões, desligamentos), troque o delta por **"X% do saldo estadual"**, ou tire o delta. Mantenha o "vs estado" só em **taxas e razões** (saldo por 10 mil hab., saída voluntária, rotatividade, gap salarial). Procure o mesmo padrão em todas as páginas, não só na Ficha.
- **Aceite:** nenhum cartão compara um valor absoluto de território com o absoluto do estado. Há teste cobrindo a função que monta o delta.

#### BUG-02 · Funil de linhas não fecha — P0
- **Problema:** na página Metodologia, o funil mostra 6.782.144 → 6.782.144 → 6.771.692 → 2.282.348, mas o texto diz "0 linhas fora do período foram excluídas". Somem 10.452 linhas sem explicação, e a ordem das etapas fica confusa no gráfico.
- **Alterar:** descubra em qual etapa as 10.452 linhas saem (exclusões EXC? salário inválido? CBO ou município nulo?). Nomeie cada etapa com o motivo da perda. Gere o texto do funil **a partir dos números**. Garanta que o gráfico mostre as etapas de cima para baixo na ordem do processo.
- **Aceite:** cada queda do funil tem um rótulo com o motivo, e a soma fecha. O texto não contradiz os números.

#### BUG-03 · Frase fixa sobre dezembro — P0
- **Problema:** "Dezembro concentra desligamentos sazonais" aparece mesmo quando o pior mês é outro (ex.: Araranguá/Veículos, pior mês jan/26; Itajaí/Veículos, pior mês out/25).
- **Alterar:** mostre a frase só quando o pior mês for dezembro. Nos outros casos, não diga nada ou use uma frase calculada.
- **Aceite:** teste com séries cujo pior mês seja e não seja dezembro.

#### BUG-04 · Formatação monetária — P0
- **Problema:** o custo de reposição aparece como "R$ 2.174,6 mi".
- **Alterar:** crie um formatador único em pt-BR para escala monetária (mil / mi / bi, uma casa decimal: "R$ 2,2 bi") e use-o em todo o painel.
- **Aceite:** teste unitário com valores nas faixas de mil, mi e bi. Nenhum valor ≥ 1 bi aparece em "mi".

#### BUG-05 · Plural errado — P0
- **Problema:** aparecem "Mesorregiãos" e "Microrregiãos" (seção "… com população parecida").
- **Alterar:** use um dicionário de plural para os níveis territoriais (Mesorregiões, Microrregiões, Municípios). Procure outros plurais montados com "+ s".
- **Aceite:** busca no código por `+ "s"` ou f-strings de plural sem ocorrências problemáticas.

#### BUG-06 · Cliques escrevem na área de transferência — P1
- **Evidência:** ao clicar em títulos de seção (ex.: o nome do território na Ficha) e em alguns controles, a página copia conteúdo para a área de transferência do usuário.
- **Alterar:** investigue a causa. Se forem os links-âncora dos títulos do Streamlit, desative com `anchor=False` em `st.header`/`st.subheader`/`st.title`, ou no equivalente em markdown. Se houver JS de cópia customizado, deixe a cópia só em botões explícitos.
- **Aceite:** clicar em títulos e controles comuns não altera a área de transferência.

#### DATA-01 · Validar a escolaridade de "Alimentos e bebidas" (−0,73 nível) — P0
- **Problema:** a diferença de escolaridade entre admitidos e desligados é −0,73 em Alimentos e bebidas, enquanto todas as outras macrofamílias ficam entre −0,12 e +0,07. Pode ser real, mas também pode ser artefato de código (no Novo CAGED existem códigos fora da escala 1–11, como "não identificado").
- **Alterar:** confira se os códigos fora de 1–11 são excluídos **antes** da média. Veja a distribuição de escolaridade por grupo. Se for artefato, corrija e registre o antes/depois. Se for real, mantenha e acrescente uma nota explicativa calculada (ex.: concentração por município/mesorregião, para o time investigar).
- **Aceite:** existe teste garantindo que só os códigos 1–11 entram na média ordinal. O CHANGELOG registra a conclusão.

---

### ÉPICO B — Rótulos, taxonomia e IA (P0/P1)

#### TAX-01 · "Veículos – Vale do Itajaí" provavelmente é construção naval — P0 (o mais importante)
- **Problema:** o principal achado de expansão ("Veículos – Vale do Itajaí, saldo 2.530, +19,3% no ano") deve vir de **estaleiros**, não de montadoras. Na microrregião de Itajaí, com o setor Veículos filtrado, o saldo é 2.609, e só jul/26 tem saldo de +1.131. Há construção naval em curso em Itajaí e Navegantes: o programa da Petrobras anunciado em 26/06/2026, os estaleiros Detroit Brasil e Navship, e as fragatas da Marinha no Estaleiro Brasil Sul (Thyssenkrupp).
- **Verificar primeiro:** quais divisões e subclasses CNAE formam o setor "Veículos" no mapeamento. Abra o saldo de Veículos no Vale do Itajaí por **divisão CNAE (29 × 30)**, por **subclasse** e por **município**.
- **Alterar, se confirmado:**
  1. Separe ou renomeie o setor. O ideal é "Veículos automotores" (div. 29) e "Construção naval e outros equipamentos de transporte" (div. 30). Se separar quebrar algo, renomeie para "Veículos e equipamentos de transporte (inclui naval)".
  2. Reescreva o achado nº 1 e a linha "Expansão mais acelerada" do Panorama com o rótulo correto.
  3. Acrescente uma nota de contexto no achado, com as fontes:
     - https://www.nsctotal.com.br/economia/contrato-bilionario-com-a-petrobras-traz-producao-de-navios-a-sc
     - https://clickpetroleoegas.com.br/petrobras-despeja-r-12-bilhoes-no-litoral-de-santa-catarina-para-construir-42-embarcacoes-reacender-estaleiros-em-itajai-e-navegantes-gerar-mais-de-5-mil-empregos-e-transformar-a-indu-asaf04/
- **Se não for confirmado:** registre no CHANGELOG o que explica o saldo (municípios e subclasses) e ajuste só o texto.
- **Aceite:** o rótulo do setor corresponde às divisões CNAE que ele contém. O achado cita o subsetor correto. O mapeamento CNAE→setor está documentado na Metodologia.

#### TAX-02 · Selo de "expansão concentrada / por projeto" — P1
- **Problema:** expansões puxadas por um projeto (estaleiro, obra) têm data para acabar e não são tendência do setor.
- **Alterar:** crie o selo **"Expansão concentrada"** quando, no grupo (território × setor), **um único mês responder por ≥ 40% do saldo positivo** ou **um único município responder por ≥ 80% do saldo**. Deixe os limiares em config. Mostre o selo nos cartões de alerta, nos achados e na ficha.
- **Aceite:** o selo aparece no caso Itajaí/Veículos (ou no setor naval, depois de TAX-01). Há teste da regra.

#### TAX-03 · Nome e erros da classificação de CBO por IA — P0 (nomes) / P1 (overrides)
- **Problemas:**
  - A macrofamília "Engenharia, técnicos industriais e TI" tem cerca de 42 mil movimentações de nível Técnico contra cerca de 4,7 mil de nível Superior, e mediana de admissão de R$ 2.836. O nome dá a entender que é dominada por engenheiros.
  - Há classificações estranhas entre as CBOs de maior volume. Exemplo: 521135 Frentista caiu em "Administrativo e comercial".
- **Alterar:**
  - **P0:** renomeie para "Técnicos industriais, engenharia e TI". Sempre que mostrar o salário dessa macrofamília, mostre também a quebra por nível (Técnico × Superior).
  - **P1:** crie `ia_cbo/overrides.csv` (colunas: `cbo, macrofamilia, nivel, justificativa, autor`), aplicado **depois** da saída da IA no pipeline. Revise as 30 CBOs de maior volume e as divergências entre rodadas de maior volume. Mostre os overrides na aba de auditoria da página "Que profissional falta", com a contagem.
- **Aceite:** nenhuma CBO entre as 30 de maior volume tem família claramente incoerente. Os overrides ficam visíveis e auditáveis.

#### TAX-04 · Texto da auditoria de IA se contradiz — P0
- **Problema:** um trecho diz que a 2ª rodada repetiu o mesmo modelo com a ordem embaralhada. Outro diz que a concordância foi medida entre "IA paga (chat)" e `cbo_macrofamilias_gemini.csv`. Além disso, a regra "em divergência, vale a 1ª rodada" não tem justificativa.
- **Alterar:** confira nos arquivos de `ia_cbo/` o que realmente aconteceu (quais modelos, quantas rodadas, que ordem) e reescreva o texto para descrever **só isso**. Justifique o critério de desempate em uma frase. **P1:** troque o desempate por uma regra explícita (ex.: prevalece a família indicada pelo prefixo da CBO; se o prefixo não resolver, override manual).
- **Aceite:** a auditoria descreve um processo só, coerente com os arquivos do repositório.

#### TAX-05 · Mostrar o que a IA acrescentou à hierarquia da CBO — P1
- **Problema:** a banca vai perguntar "por que usar IA se a CBO já tem hierarquia?". Hoje o painel diz que "justificativa vazia = a IA seguiu o prefixo".
- **Alterar:** na auditoria, mostre **quantas CBOs e quantas movimentações a IA classificou de forma diferente da família sugerida pelo prefixo**, com 5 exemplos de alto volume e a justificativa de cada um.
- **Aceite:** existe um número claro de "decisões da IA além do prefixo", com exemplos.

#### TAX-06 · Script reproduzível de classificação — P1
- **Problema:** o guia pede o pipeline "até a comunicação com a API de IA/prompts". A classificação foi feita via chat.
- **Alterar:** acrescente `ia_cbo/classificar.py`, que recebe a lista de CBOs e o prompt já usado (mesmo arquivo de prompt) e chama a API em lotes, salvando as respostas no mesmo formato. Pegue a chave de API de variável de ambiente e nunca a grave no repositório. **Não rode o script agora;** documente no README que a execução oficial foi via chat e que os prompts e respostas estão versionados.
- **Aceite:** o script existe, tem `--help`, e o README explica as duas formas de execução.

---

### ÉPICO C — Responder à pergunta central (narrativa) (P0)

#### NAR-01 · Quadrantes alinhados à definição do guia — P0
- **Problema:** hoje "Apagão (rotatividade crônica)" é o quadrante "perde gente e cresce pouco", o que é retração com rotatividade. Pelo guia, apagão é **alta demanda + escassez ou rotatividade**, ou seja, o quadrante que **cresce e perde gente** (hoje chamado "Expansão sob pressão").
- **Alterar** (rótulos centralizados, ver regra 5):

  | Quadrante (eixos atuais) | Rótulo novo |
  |---|---|
  | Cresce muito + perde a equipe | **Apagão: cresce, mas não retém** |
  | Cresce muito + segura a equipe | **Expansão acelerada** |
  | Cresce pouco + perde a equipe | **Retração com rotatividade** |
  | Cresce pouco + segura a equipe | **Estagnação** |

  Atualize legenda, cores, cartões de alerta, contagens ("X grupos em…"), textos de achados, recomendações, Metodologia e o CSV exportado. Se algum texto ou regra depender do nome antigo, ajuste a lógica, não só a string.
- **Aceite:** busca por "rotatividade crônica" e "Expansão sob pressão" sem resultado no código. As contagens por quadrante batem entre gráfico, texto e CSV.

#### NAR-02 · Título que responde às duas metades da pergunta — P0
- **Problema:** o título do Panorama ("…o apagão é de retenção, não de falta de contratação") responde ao "onde", mas não diz **se renda e escolaridade explicam**.
- **Alterar:** acrescente ao topo do Panorama um bloco **"Resposta à pergunta central"** com 3 linhas, todas **calculadas**:
  1. **Onde:** território × setor em Apagão e em Expansão acelerada (top 1–2 de cada, com saldo e rotatividade).
  2. **Renda explica?** Use a correlação entre gap salarial e saída voluntária (hoje −0,35) e a contagem de grupos com causa salarial (depois de ANA-01). Expresse como "explica em parte" ou "não explica", segundo limiares definidos em config e documentados.
  3. **Escolaridade explica?** Use o gap de escolaridade (hoje −0,05 nível no estado) e o número de grupos com causa de qualificação. Expresse da mesma forma.
- **Aceite:** um diretor lê a resposta completa sem rolar a página. Todo número do bloco vem de cálculo e muda com os filtros.

#### NAR-03 · Separar Construção da indústria de transformação — P0
- **Problema:** os 5 primeiros alertas são de Construção (seção F), cuja rotatividade é estrutural (fim de obra). A banca e a Federação das Indústrias querem ver a transformação (têxtil, metalmecânica, alimentos, eletroeletrônico), o parque que o guia descreve.
- **Alterar:**
  1. Acrescente ao filtro "Escopo" a opção **"Indústria de transformação (C)"** e use-a como **padrão de abertura**. Mantenha "Indústria (B–F)" e "Toda a economia".
  2. Em "Quem precisa de atenção", quando o escopo incluir F, mostre os alertas em **duas listas**: "Transformação" e "Construção (rotatividade estrutural de obra)".
  3. No Panorama, a linha "Maior tensão" mostra o maior grupo da **transformação** e, se o escopo incluir F, também o da construção, com o aviso de que ela é estrutural.
- **Aceite:** ao abrir o painel, os alertas do topo são da transformação. Construção continua acessível, mas identificada.

#### NAR-04 · Linguagem executiva e remoção de termos internos — P0
- **Remover ou trocar** em todas as páginas:
  - "ClienteArquivo", "IA paga (chat)", "PLANEJAMENTO §7.1" → texto neutro ("classificação feita via interface de chat do modelo X; prompts e respostas versionados em `ia_cbo/`").
  - Tabela "Requisitos do desafio R1–R9" → reestruture como **"Onde conferir cada critério da banca"**, com as 5 dimensões oficiais (Compreensão, Embasamento, Dashboard, Recomendações, Pitch) e, para cada uma, as páginas e seções que a atendem. Os itens técnicos (Azure, testes, reprodutibilidade) ficam numa subseção "Engenharia".
  - Jargão sem explicação: "rotatividade descontada", "p.p.", "z-score", "Dinamismo", "Tensão". Acrescente tooltip (`help=`) com uma frase simples em cada KPI, e um **glossário** curto no fim da Metodologia.
- **Aceite:** busca pelos termos internos sem resultado nas strings de interface. Todo KPI tem `help`.

#### NAR-05 · Mapa abre em nível de mesorregião — P1
- **Problema:** o mapa abre por município, com círculos de volume, e fica poluído na visão geral. O "pior caso" destacado é um município pequeno (Campo Alegre, −332,9 por 10 mil hab.).
- **Alterar:** abra o mapa em **Mesorregião**, com o volume desligado. Na frase "Pior situação", use o nível escolhido e, para município, exija um volume mínimo maior (configurável, ex.: ≥ 500 movimentações).
- **Aceite:** a primeira tela é legível no projetor, a 1 metro de distância.

---

### ÉPICO D — Embasamento analítico (P0/P1)

#### ANA-01 · Viés de tempo de casa no indicador "quem entra ganha menos que quem sai" — P0
- **Problema:** quem sai tem mais tempo de casa, então o salário de entrada ser menor é o esperado. Com o corte fixo em 0,95, **55 de 82 grupos** recebem o selo de causa "Salarial", e o selo perde poder de discriminação.
- **Alterar (P0, sem reprocessar microdados):** troque o critério absoluto por um **relativo ao estado**. Um grupo tem causa "Salarial" quando a razão entrada/saída for **pelo menos 3 p.p. pior que a razão do estado inteiro** no mesmo recorte de escopo e período (limiar em config). Mostre ao lado a razão do estado como referência.
- **Alterar (P1):** calcule a razão **dentro da mesma CBO** (média ponderada das razões por CBO dentro do grupo, só CBOs com ≥ 30 salários de cada lado), se os agregados tiverem a CBO. Assim a comparação é entre a mesma função. Se depender de reprocessar, só faça depois do P0.
- **Documentar:** na Metodologia, explique o viés de tempo de casa e a correção adotada.
- **Aceite:** a contagem de grupos com causa salarial muda e fica registrada no CHANGELOG (antes 55/82). O texto do critério na tela corresponde à regra nova.

#### ANA-02 · Escolaridade além da média ordinal — P1
- **Problema:** a média dos códigos 1–11 é pouco sensível, e o painel não mostra se a indústria está contratando nível técnico e superior.
- **Alterar:** acrescente, por grupo e por macrofamília, a **participação de admitidos com Médio completo ou mais** e **com Superior completo** contra a dos desligados, e o **prêmio salarial por escolaridade** (mediana do Superior ÷ mediana do Médio). Na página "Por que acontece", destaque onde o prêmio é baixo, um possível sinal de desatratividade para qualificados.
- **Aceite:** existe pelo menos um gráfico ou cartão novo respondendo "o mercado está contratando mais instruídos e pagando mais?", que é o eixo socioeconômico do guia.

#### ANA-03 · Proxy de demanda — P1
- **Problema:** apagão pressupõe demanda, e o eixo X usa só crescimento.
- **Alterar:** calcule a **taxa de admissão** (admissões ÷ estoque em 31/12/2025) por grupo. Mostre-a no tooltip e na tabela de alertas. Na Metodologia, explique que demanda alta + retenção baixa é o sinal de apagão.
- **Aceite:** a taxa aparece nas tabelas e tem definição na Metodologia.

#### ANA-04 · Benchmark SC × Brasil para saída voluntária — P2
Registre no roadmap: comparar a saída voluntária e a rotatividade por seção com o Brasil (tabelas oficiais do CAGED), para separar o estrutural do local. Inclua também intervalos de confiança por bootstrap (já listados em "Próximos passos").

---

### ÉPICO E — Recomendações e valor de negócio (P0/P1)

#### REC-01 · Nova alavanca "Formação profissional direcionada" — P0
- **Problema:** não há nenhuma recomendação de formação, que é o primeiro exemplo do guia e o tema central de um evento UniSENAI/SENAI. Também é o que mais liga as recomendações às **macrofamílias da IA**, exigência explícita do critério 4.
- **Alterar:** crie a alavanca com uma regra explícita (limiares em config). Exemplo: grupo (mesorregião × macrofamília) **em Apagão ou Expansão acelerada**, com **nível-alvo Qualificado ou Técnico**, **e** pelo menos um destes: gap de escolaridade < 0, desligamento precoce acima do estado, ou participação de Técnico/Superior entre admitidos menor que entre desligados.
  - Para cada recomendação, liste **as 3–5 CBOs de maior volume** do grupo (código + descrição). Elas são o "o que formar".
  - Descreva a ação de forma genérica e verificável: "turmas de qualificação/aprendizagem industrial para as ocupações X, Y, Z na mesorregião W". **Não invente nomes de cursos** que não estejam num arquivo de referência do repositório.
- **Aceite:** a alavanca aparece em "O que fazer", com pelo menos uma recomendação e a evidência de cada uma. A regra está documentada.

#### REC-02 · Recomendações com responsável, prazo e meta — P0
- **Alterar:** acrescente à tabela de recomendações, e às fichas exportadas, as colunas:
  - **Quem age:** Empresa / Federação–SENAI / Poder público (mapeado por alavanca, em config).
  - **Horizonte:** 0–3 / 3–12 / 12+ meses.
  - **KPI de acompanhamento + meta:** ex.: "saída voluntária do grupo de 59% → 50% em 12 meses", com a meta calculada como uma fração da distância até a média estadual, configurável.
- **Aceite:** toda recomendação tem as três colunas preenchidas, e os CSVs exportados as incluem.

#### REC-03 · Definir ou renomear "Recrutamento inter-regional" — P0
- **Problema:** o painel diz "a mesma profissão sobra numa região e falta em outra", mas o CAGED não mede sobra de mão de obra.
- **Alterar:** escreva a regra de forma explícita e calculável. Exemplo: mesma macrofamília e nível, com **região de origem** em retração (saldo < 0, saída voluntária abaixo do estado) e **região de destino** em Apagão. Mostre **pares origem → destino**. Se não der para sustentar uma regra assim com os dados disponíveis, renomeie a alavanca para algo honesto ("Atração de talentos de outras regiões") e tire a frase sobre "sobra".
- **Aceite:** a frase na tela corresponde à regra do código, e a regra está na Metodologia.

#### REC-04 · Top 3 executivo no início de "O que fazer" — P0
- **Alterar:** acima dos cartões de prioridade, mostre **as 3 recomendações de maior impacto** (por movimentações afetadas × prioridade). Cada uma em uma linha: ação + onde + evidência numérica + quem age. É a tela que o pitch vai mostrar.
- **Aceite:** o bloco é legível em 15 segundos e muda com os filtros.

#### REC-05 · Simulador de custo com premissa citada — P1
- **Alterar:** use o formatador de BUG-04 e acrescente o intervalo da premissa (custo de reposição em salários) com a fonte usada. Se não houver fonte no repositório, escreva "premissa do time, ajuste conforme a realidade da empresa", sem inventar referência. Deixe claro que o cálculo assume que todo desligamento a pedido é reposto.
- **Aceite:** a premissa e a limitação aparecem na tela.

#### REC-06 · Revisar a alavanca "Automação" — P1
- **Problema:** existe só uma recomendação (Serviços de apoio · Sul).
- **Alterar:** revise a regra. Se ela continuar gerando 0–1 casos, mostre-a como "observação" em vez de alavanca prioritária, ou ajuste o limiar com justificativa documentada.

---

### ÉPICO F — Entregáveis, infraestrutura e prontidão para o pitch (P0)

#### ENT-01 · Link do repositório público — P0
- **Problema:** a Metodologia cita "commit 3fd2dfb", mas não tem link. O repositório Git público é entregável obrigatório.
- **Alterar:** coloque o link do repositório na barra lateral (rodapé) e na Metodologia, com o hash do commit linkando para o commit. Confirme que o repositório está **público** e que o README explica como rodar o pipeline e o painel.
- **Aceite:** o link abre o repositório sem login.

#### ENT-02 · Disponibilidade no Azure — P0
- **Alterar:** confira se o App Service está com **Always On** habilitado (se o plano permitir), para evitar a primeira carga lenta no pitch. Se não der, documente no README e no checklist do pitch que alguém deve abrir o painel 10 minutos antes.
- **Aceite:** registrado no CHANGELOG.

#### ENT-03 · Deploy e smoke test — P0 (último passo)
1. Rode todos os testes.
2. Se o pipeline mudou, regenere os agregados e publique no Blob.
3. Faça o deploy no App Service.
4. Abra **as 7 páginas** no endereço público e confira:
   - Panorama, com a "Resposta à pergunta central";
   - Quem precisa de atenção, com os rótulos novos e as listas separadas;
   - Por que acontece;
   - Que profissional falta;
   - O que fazer, com o Top 3 e a alavanca de formação;
   - Ficha do território, com o "vs estado" corrigido;
   - Metodologia, com o funil corrigido, o link do repositório e o mapa de critérios.
5. Teste também um recorte vazio (filtros sem dados) e confira que o aviso aparece sem erro.

#### ENT-04 · Material de apoio para o pitch — P0
Gere `docs/PITCH_APOIO.md` com:
- **Os números finais** que o time vai falar (título, top 2 apagões, top 2 expansões, resposta sobre renda e escolaridade, Top 3 recomendações, custo estimado), copiados do painel **depois** do deploy.
- **Roteiro de telas para 3 minutos:** Panorama (resposta + mapa) → Quem precisa de atenção (quadrante) → O que fazer (Top 3). O resto fica para as perguntas.
- **Respostas curtas (2–3 frases, com o número)** para as perguntas prováveis da banca:
  1. Por que vocês chamam de apagão o que o CAGED mostra como rotatividade, se ele não mede vagas abertas?
  2. Quem sai não ganha mais só por ter mais tempo de casa? (ver ANA-01)
  3. Por que usar IA se a CBO já tem hierarquia? (ver TAX-05)
  4. A expansão em Itajaí é tendência ou é projeto? (ver TAX-01/TAX-02)
  5. Por que reconstruir a base pelo FTP do MTE em vez de usar a fornecida? (diferença de +0,02% nas admissões e +0,005% nos desligamentos)
  6. Construção tem rotatividade estrutural; por que ela aparece? (ver NAR-03)
  7. Qual a recomendação mais barata e de maior impacto?

---

## 3. Ordem de execução sugerida (P0)

| Ordem | Itens | Motivo |
|---|---|---|
| 1 | Exploração + `MAPA_DO_CODIGO.md` | Evita retrabalho |
| 2 | TAX-01, DATA-01 | Investigações que podem mudar números e textos de tudo o que vem depois |
| 3 | BUG-01 a BUG-05 | Correções rápidas e de baixo risco |
| 4 | NAR-01, NAR-03 | Mudam a classificação e o escopo padrão, que são a base dos textos |
| 5 | ANA-01 | Muda a contagem de causas usada em NAR-02 e nas recomendações |
| 6 | REC-01, REC-02, REC-03, REC-04 | Dependem dos quadrantes e das causas novos |
| 7 | NAR-02, NAR-04, TAX-03 (nome), TAX-04 | Textos finais, depois que os números estabilizam |
| 8 | ENT-01, ENT-02, ENT-03 | Publicação e verificação |
| 9 | ENT-04 | Usa os números finais publicados |
| 10 | P1, se sobrar tempo, na ordem: TAX-02, ANA-02, TAX-05, NAR-05, TAX-03 overrides, ANA-03, REC-05, REC-06, BUG-06, TAX-06 | |

Se o tempo acabar no meio de um item P0, **reverta esse item** em vez de publicar pela metade. Painel consistente vale mais que painel completo.

---

## 4. Definição de pronto

- [ ] Todos os P0 implementados ou, se a hipótese se mostrou falsa, justificados no CHANGELOG.
- [ ] Suíte de testes passando, com testes novos para as regras alteradas.
- [ ] Nenhum termo interno nem rótulo antigo na interface (buscas de NAR-01 e NAR-04 vazias).
- [ ] Todo número em texto vem de cálculo e reage aos filtros.
- [ ] Painel publicado no Azure, com as 7 páginas conferidas no endereço público.
- [ ] `docs/CHANGELOG_BANCA.md` com o antes/depois dos números do pitch.
- [ ] `docs/PITCH_APOIO.md` gerado com os números finais.
- [ ] Itens P2 registrados em `docs/ROADMAP.md`.

## 5. Relatório final (ao terminar)

Responda com:
1. A lista de itens feitos, com o commit de cada um.
2. As hipóteses que **não** se confirmaram e o que foi encontrado.
3. A tabela de antes/depois dos números que aparecem no pitch.
4. Os itens que ficaram de fora e por quê.
5. Os riscos conhecidos que o time precisa saber antes de subir ao palco.
