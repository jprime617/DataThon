# Continuidade do plano da banca (Lotes D e C)

Documento de passagem entre sessões. Leia junto com `PLANO_CORRECOES_DATATHON.md`
(o plano), `docs/CHANGELOG_BANCA.md` (o que foi feito, com números de antes e
depois) e `docs/MAPA_DO_CODIGO.md` (onde fica cada coisa).

## Onde paramos

- **Lotes A e B concluídos**, com um commit por item, mergeados em
  `dashboard-v2` e enviados ao GitHub. A suíte passa (338 testes, 6 pulados
  por falta da base fornecida em `Dados/`).
- **Nada foi publicado ainda:** nem no Azure Blob nem no App Service. A
  produção ainda mostra a versão antiga.
- Ordem combinada com o usuário: **Lote D (P1 + ANA-04) → Lote C
  (publicação)**, pedindo o aval dele entre os lotes. O usuário pediu para
  implementar **tudo**, incluindo o P2 ANA-04.
- A branch `panorama-decisao` guarda um redesenho antigo do Panorama (WIP).
  Ela **não** entra no pitch; não mexa.

## Regras de trabalho (do plano, seção 1, e combinadas com o usuário)

- Branch de trabalho: `fix/banca`, a partir de `dashboard-v2`. Um item por
  commit, com o ID na mensagem (`TAX-02: ...`). Terminado o lote, merge em
  `dashboard-v2` e push.
- Nenhum número escrito à mão em texto da tela: tudo calculado e reagindo
  aos filtros. Fato externo só com a fonte citada na tela.
- Rótulos, limiares e regras ficam **só em `dashboard/regras.py`**
  (reexportados por `dashboard/comum.py`).
- Toda regra nova ou alterada ganha teste. Depois de cada item, rodar
  `python -m pytest -q`.
- Verificação visual de cada tela alterada, com filtro padrão e com recorte
  vazio. Usamos Playwright + Chromium headless (`pip install playwright &&
  python -m playwright install --with-deps chromium`) e `streamlit run
  dashboard/app.py` em segundo plano. Tire o `AZURE_STORAGE_CONNECTION_STRING`
  do ambiente para ler a cópia local.
- Atualizar `docs/CHANGELOG_BANCA.md` a cada item, com antes e depois dos
  números.
- Hipótese que não se confirma não é forçada: registre no CHANGELOG e siga.
- Não rodar o LLM de novo para reclassificar as CBOs. Correções pontuais vão
  por `ia_cbo/overrides.csv` (TAX-03 P1).
- No fim de cada lote: relatório ao usuário (itens com commit, hipóteses não
  confirmadas, antes e depois, riscos) e pedir aval para o próximo lote.

## Preparar a máquina nova

```bash
git clone https://github.com/jprime617/DataThon && cd DataThon
git checkout dashboard-v2 && git checkout -b fix/banca-d   # ou continue em fix/banca
pip install -r requirements.txt
python -m pytest -q                                          # deve passar
```

Os artefatos agregados (`data_processed/*.parquet`, incluindo o novo
`caged_cbo.parquet`) estão versionados: o painel roda sem baixar nada.

**Só para reprocessar o pipeline** (necessário no Lote D: overrides de CBO e
razão salarial dentro da mesma CBO), os microdados precisam ser baixados de
novo. Eles não vão para o Git: são uns 6 GB em `data/`.

```bash
python -m src.download                 # 72 .7z do CAGED (MOV/FOR/EXC); retomável; o FTP do MTE cai às vezes: rode de novo
python scripts/baixar_rais.py          # RAIS 2025 Sul (705 MB) + extração; retomável
python -m src.rais && python -m src.rais --estoque
python -m src.caged24                  # consolidado de SC → data/interim/caged_sc_24m.parquet
# Com 8 GB de RAM a limpeza morre sem swap (o kernel do notebook cai):
sudo fallocate -l 8G /tmp/swapfile && sudo chmod 600 /tmp/swapfile && sudo mkswap /tmp/swapfile && sudo swapon /tmp/swapfile
# Faça commit do código ANTES de rodar: o metadados.json grava o hash do HEAD.
PULAR_UPLOAD=1 python -m jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=4800 notebooks/01_pipeline.ipynb
```

Depois de reprocessar, confira que os totais não mudaram: 3.443.428
admissões, 3.328.264 desligamentos e estoque de 2.565.458. Também a CBO:
a tabela `caged_cbo.parquet` fecha com o agregado.

## Decisões já tomadas (não reabrir sem motivo)

- **Escopo de abertura:** Indústria de transformação (C). Construção (F)
  aparece separada, como rotatividade estrutural.
- **Quadrantes** (NAR-01): Apagão = cresce e não retém; Expansão acelerada;
  Retração com rotatividade; Estagnação. Os eixos são relativos à média dos
  grupos, por isso as frases só citam como Apagão grupos com saldo > 0.
- **Setores 29 e 30 separados** (TAX-01): "Veículos automotores e autopeças"
  e "Construção naval e outros equipamentos de transporte". A expansão do
  Vale do Itajaí é 63% autopeças (Navegantes, subclasse 2945-0) e 37% naval.
  As fontes sobre estaleiros estão citadas na tela. **Fragatas e Estaleiro
  Brasil Sul não aparecem nas fontes e ficaram fora.**
- **Causa Salarial relativa ao estado** (ANA-01): ≥ 3 p.p. pior que a razão
  do estado. A referência é sempre `Contexto.ref` (estado, mesmo escopo e
  período).
- **Formação** (REC-01): com limiares de materialidade; sem as famílias
  administrativas e de apoio.
- **Top 3** (REC-04): uma ação por alavanca, de grupos distintos.
- **IA** (TAX-04): a 1ª rodada (claude-opus-5-5 via chat) vale; a 2ª é a
  classificação anterior via API do gemini-3.1-flash-lite (auditoria). O
  nome antigo "Engenharia, técnicos industriais e TI" é alias do novo.

## Lote D (P1 + ANA-04): o que falta

Na ordem do plano (seção 3, linha 10), com as notas do que já se sabe:

1. **TAX-02** · Selo "Expansão concentrada": um mês ≥ 40% do saldo positivo
   **ou** um município ≥ 80% do saldo, com limiares em `regras.py`. Deve
   acender em autopeças – Vale do Itajaí (100% Navegantes). Já existe
   `narrativa.concentracao_municipio`; aproveite. Mostrar o selo nos cartões
   de alerta, nos achados e na ficha.
2. **ANA-02** · Participação de admitidos × desligados com Médio completo ou
   mais e com Superior completo, e o prêmio salarial (mediana Superior ÷
   Médio), por grupo e macrofamília. O `caged_perfil.parquet` já tem
   `faixa_escolaridade` e medianas. Destaque em "Por que acontece" onde o
   prêmio é baixo.
3. **TAX-05** · Quantas CBOs e movimentações a IA classificou **diferente da
   família sugerida pelo prefixo** (`src.mapeamentos.FAMILIA_POR_PREFIXO_CBO`,
   `src.cbo_ia.familia_sugerida`), com 5 exemplos de alto volume e a
   justificativa (coluna `justificativa` do `cbo_macrofamilias.csv`).
   Mostrar na aba de auditoria de "Que profissional falta".
4. **NAR-05** · O mapa abre em Mesorregião com o volume desligado. "Pior
   situação" usa o nível escolhido; em município, exigir ≥ 500 movimentações
   (configurável).
5. **TAX-03 (overrides)** · `ia_cbo/overrides.csv` (colunas `cbo,
   macrofamilia, nivel, justificativa, autor`), aplicado **depois** da saída
   da IA no pipeline (em `cbo_ia.aplicar_mapeamento`, ou logo depois no
   notebook). Revisar as 30 CBOs de maior volume e as divergências de maior
   volume (`data_processed/cbo_divergencias.csv`). O caso conhecido é 521135
   Frentista em "Administrativo e comercial". Mostrar a contagem de
   overrides na auditoria. **Pede reprocessamento.**
6. **ANA-03** · Taxa de admissão = admissões ÷ estoque em 31/12/2025, por
   grupo, no tooltip da matriz e na tabela de alertas, com definição na
   Metodologia. O estoque já está no agregado (`M_ESTOQUE`).
7. **REC-05** · Simulador de custo: usar o formatador `fmt_brl_escala` (já em
   uso), mostrar o intervalo da premissa e a fonte. Não há fonte no repo,
   então escrever "premissa do time, ajuste conforme a realidade da
   empresa". Dizer que o cálculo assume que todo desligamento a pedido é
   reposto.
8. **REC-06** · Automação gera hoje 1 recomendação. Mostrar como
   "observação", ou ajustar o limiar com justificativa.
9. **BUG-06** · Cliques que copiam para a área de transferência: investigar
   (provavelmente os links-âncora dos títulos) e usar `anchor=False` em
   `st.title`, `st.header` e `st.subheader`.
10. **TAX-06** · `ia_cbo/classificar.py` com `--help`: lê a lista de CBOs e
    o mesmo prompt e chama a API em lotes, com a chave por variável de
    ambiente. **Não executar.** O README explica as duas formas (chat
    oficial e API).
11. **ANA-01 P1** · Razão salarial entrada/saída **dentro da mesma CBO**
    (média ponderada das razões por CBO, só CBOs com ≥ 30 salários de cada
    lado). Já dá para fazer com `caged_cbo.parquet`, que tem soma e n de
    salário por CBO e mês, **sem reprocessar**. Atualizar a frase da
    Metodologia que diz "é o passo seguinte".
12. **TAX-04 P1** · Regra explícita de desempate: prevalece a família do
    prefixo da CBO; se o prefixo não resolve, override manual.
13. **ANA-04 (P2, pedido pelo usuário)** · SC × Brasil para saída voluntária
    e rotatividade por seção. Os `.7z` do CAGED baixados são **nacionais**:
    dá para calcular o Brasil sem fonte nova (hoje `src.caged24` filtra
    `uf == 42`). Também intervalos de confiança por bootstrap. Registrar em
    `docs/ROADMAP.md` o que não couber.

Fazer os itens de painel primeiro (1–4, 6–9, 11) e juntar os que exigem
pipeline (5, 12) **numa única execução**.

## Lote C: publicação (precisa do usuário)

- **ENT-01:** link do repositório na barra lateral e na Metodologia, com o
  hash do commit linkado (variável `DASHBOARD_REPO_URL` já existe na
  Metodologia). Confirmar que o repositório é público.
- **ENT-02:** Always On no App Service, ou o checklist "abrir o painel 10
  minutos antes".
- **ENT-03:** testes → upload ao Blob de **5** artefatos juntos:
  `caged_agregado`, `caged_perfil`, `caged_cbo`, `rais_estoque` e
  `metadados.json`. O comando do README ainda lista 4; incluir
  `caged_cbo.parquet` (`NOME_BLOB_CBO` em `comum.py`). Depois, o deploy do
  App Service (`az webapp deploy`, README seção 3) e a conferência das 7
  páginas no endereço público, inclusive com recorte vazio.
  - Precisa de `AZURE_STORAGE_CONNECTION_STRING` num `.env`, que está no
    `.gitignore`; **nunca cole a chave no chat**.
  - Precisa de `az login` feito pelo usuário.
- **ENT-04:** `docs/PITCH_APOIO.md` com os números finais copiados do painel
  publicado, o roteiro de 3 minutos e as 7 respostas para a banca.
- Registrar os P2 restantes em `docs/ROADMAP.md`.
- Relatório final no formato da seção 5 do plano. O swap temporário, se
  criado, deve ser desligado (`sudo swapoff /tmp/swapfile && sudo rm
  /tmp/swapfile`).

## Riscos conhecidos

- `tests/test_agregador_exportacao.py::test_prop24_round_trip_de_exportacao_do_agregado`
  (Hypothesis) falhou uma vez com a máquina carregada e passou em todas as
  repetições. É instável, não regressão.
- O FTP do MTE derruba conexões. Os scripts de download retomam: é só rodar
  de novo.
- Sem `caged_cbo.parquet` no Blob, a produção mostra a formação sem a lista
  de CBOs (com aviso). Ele precisa subir junto com os outros.
