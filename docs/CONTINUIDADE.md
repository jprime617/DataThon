# Continuidade do plano da banca (Lotes D e C)

Documento de passagem entre sessões. Leia junto com `PLANO_CORRECOES_DATATHON.md`
(o plano), `docs/CHANGELOG_BANCA.md` (o que foi feito, com números de antes e
depois) e `docs/MAPA_DO_CODIGO.md` (onde fica cada coisa).

## Onde paramos

- **Lotes A, B e D concluídos**, com um commit por item, mergeados em
  `dashboard-v2` e enviados ao GitHub. O Lote D foi feito na branch
  `fix/banca-d`. Itens: TAX-02, ANA-02, TAX-05, NAR-05, ANA-03, REC-05,
  REC-06, BUG-06, TAX-06, ANA-01 P1, TAX-04 P1, TAX-03 overrides, o
  reprocessamento e ANA-04. Detalhes, antes e depois: `docs/CHANGELOG_BANCA.md`.
- **O pipeline foi reprocessado** no Lote D (overrides e desempate): os
  artefatos de `data_processed/` são novos e o `metadados.json` aponta o
  commit. Totais conferidos: 3.443.428 admissões, 3.328.264 desligamentos,
  estoque de 2.565.458.
- **Novos artefatos que o painel lê da cópia local (vão no deploy, não no
  Blob):** `data_processed/cbo_classificacao_final.csv` (classificação final
  com a origem de cada decisão) e `data_processed/caged_brasil_secao.parquet`
  (benchmark SC × Brasil).
- **Nada foi publicado ainda:** nem no Azure Blob nem no App Service. A
  produção ainda mostra a versão antiga. **Próximo passo: Lote C, com o
  usuário** (credencial do Azure e `az login`).
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

## Lote D (P1 + ANA-04): feito

Ver `docs/CHANGELOG_BANCA.md` (seção "Lote D"). Pontos que mudam a fala do
pitch ou que o time precisa validar:

- **TAX-04 P1:** a regra "prevalece sempre o prefixo" **não** foi adotada ao
  pé da letra (reverteria 102 desvios justificados, como o 766 gráfica →
  Têxtil). Regra adotada: o prefixo desempata, mas o desvio justificado da
  1ª rodada vale; se o prefixo não resolve, a CBO vai para revisão manual.
- **TAX-03:** 12 overrides em `ia_cbo/overrides.csv`, com autor "revisão
  assistida, a validar pela equipe". O único que muda dado é o Frentista
  (nível Básico → Qualificado); a família dele é coerente com a CBO 5211.
- **ANA-01 P1:** a causa Salarial usa a razão **dentro da mesma CBO**. A
  chave `regras.RAZAO_SALARIAL_MESMA_CBO` volta para a razão bruta.
- **ANA-04:** a saída voluntária de SC está muito acima da do Brasil
  (+13,6 p.p. na transformação), mas a rotatividade é igual (27,4% × 27,6%).
- **REC-06:** a automação virou observação, fora do Top 3.
- O que não coube está em `docs/ROADMAP.md`.

Para reprocessar de novo: os microdados não vão para o Git. Use as
instruções de "Preparar a máquina nova" e rode também
`python -m src.caged_brasil` (relê os 72 `.7z`; ~15 min) se quiser
regenerar o benchmark nacional.

## Lote C: publicação (precisa do usuário)

- **ENT-01:** link do repositório na barra lateral e na Metodologia, com o
  hash do commit linkado (variável `DASHBOARD_REPO_URL` já existe na
  Metodologia). Confirmar que o repositório é público.
- **ENT-02:** Always On no App Service, ou o checklist "abrir o painel 10
  minutos antes".
- **ENT-03:** testes → upload ao Blob de **5** artefatos juntos (os dois
  arquivos novos do Lote D, `cbo_classificacao_final.csv` e
  `caged_brasil_secao.parquet`, são lidos da cópia local e vão no pacote do
  App Service):
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
