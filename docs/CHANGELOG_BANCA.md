# Changelog para a banca

Um registro por item do `PLANO_CORRECOES_DATATHON.md`: o que mudou, onde, e os
números de antes e depois de todo indicador que aparece no pitch.

Recorte de referência dos números (o padrão de abertura do painel, salvo
indicação): escopo Indústria (B–F), set/25–ago/26, Santa Catarina inteira.

---

## DATA-01 · Escolaridade de "Alimentos e bebidas" (−0,73 nível)

**Conclusão: o número é real, não é erro de código.** Mantido.

- **Códigos fora da escala:** `limpeza.derivar_escolaridade_ordinal` mapeia
  só 1–11 (e 80 = pós-graduação → 9,5). Qualquer outro código (ex.: 99, não
  identificado) vira NaN, e `agregador.preparar_base` só soma e conta valores
  não nulos. Novo teste ponta a ponta: `tests/test_agregador_v2.py::test_media_de_escolaridade_so_usa_codigos_validos`.
- **O gap é persistente:** fica entre −0,46 e −0,89 em **todos os 24 meses**
  (set/24–ago/26), sem pico isolado.
- **O gap é concentrado:** 71% das admissões da macrofamília (12 meses) estão
  no **Oeste Catarinense**, onde o gap é −0,95. Nas outras mesorregiões ele
  fica entre −0,23 e +0,11. Os maiores municípios são Chapecó (−1,12), Guatambú
  (−1,31) e Concórdia (−0,34). Xaxim (−1,82), Abelardo Luz (−1,22) e Quilombo
  (−1,27) também puxam para baixo.
- **Distribuição:** com até o fundamental incompleto estão **35,0% dos
  admitidos contra 25,6% dos desligados**. Com médio completo, 30,7% contra
  41,9% (período inteiro, perfil).
- Na comparação, as demais macrofamílias ficam entre −0,12 e +0,07.

**O que mudou na tela:** em "Por que acontece" → "Aprofundar: qualificação e
retenção", abaixo do gráfico de gap por macrofamília, entra uma nota
**calculada** (`narrativa.destaque_escolaridade`). Ela aparece quando uma
macrofamília tem gap ≤ `LIMIAR_DESTAQUE_GAP_ESC` (−0,30, em `comum.py`) e diz
onde as admissões se concentram e qual a faixa de escolaridade. Também reage
aos filtros.

**Para o time investigar (não está na tela):** a concentração em polos de
abate e processamento de carnes do Oeste sugere uma mudança no perfil de
contratação (ex.: mais trabalhadores com escolaridade baixa ou não comprovada).
O CAGED não mostra a causa.

| Indicador | Antes | Depois |
|---|---|---|
| Gap de escolaridade, Alimentos e bebidas (indústria, 12 meses) | −0,73 | −0,73 (sem mudança) |

---

## BUG-01 · "vs estado" em métricas absolutas

- `comum.delta_texto` agora devolve `None` para `METRICAS_ABSOLUTAS`
  (movimentações, saldo e estoque): nenhum absoluto de território é subtraído
  do absoluto do estado. O delta "vs estado/vs SC" fica só em taxas e razões.
- Nova `comum.participacao_estadual`: mostra "36,7% do estado", em
  cinza e sem seta. Com sinais opostos (o território fechou vagas e o estado
  abriu), mostra só "estado: 2.726".
- Onde se aplica: Ficha do território (cartão Saldo), cartões de alerta de
  "Quem precisa de atenção" (Saldo de vagas) e `cartoes_kpi` (todas as
  páginas, quando há recorte).
- Testes: `test_delta_recusa_metricas_absolutas`,
  `test_participacao_estadual_no_mesmo_sinal_e_com_sinais_opostos`.

| Tela | Antes | Depois |
|---|---|---|
| Ficha, Grande Florianópolis, Saldo | −1.913 · "−4.639 vs estado" | −1.913 · "estado: 2.726" |

---

## BUG-02 · Funil de linhas não fechava

- **Onde saíam as 10.452 linhas:** o bruto tem MOV + FOR + EXC. Cada linha
  EXC (exclusão declarada) tem peso −1 em `agregador.preparar_base`: ela sai
  e anula a declaração que corrige. A queda entre as linhas no período e as
  movimentações é, portanto, 2 × EXC (10.452 = 2 × 5.226). **Conferido nos
  microdados:** o consolidado de 24 meses tem exatamente 5.226 linhas EXC
  (MOV 6.715.601 + FOR 61.317 + EXC 5.226 = 6.782.144).
- **Pipeline:** `montar_metadados(linhas_por_tipo=...)` grava
  `linhas.por_tipo` (MOV, FOR, EXC) no `metadados.json`, e o notebook passa a
  contagem por `tipo_arquivo`. Com isso, o funil confere `perda == 2 × EXC`
  e mostra qualquer sobra como "outras perdas".
- **Painel:** `narrativa.etapas_funil` monta as etapas na ordem do processo,
  cada queda com o motivo. `narrativa.texto_funil` gera a legenda a partir
  dos números (some o "0 linhas fora do período foram excluídas" sem
  contexto). O gráfico fixa a ordem de cima para baixo e mostra a perda de
  cada etapa.
- Testes: `test_funil_fecha_a_soma_e_nomeia_cada_queda`,
  `test_funil_mostra_a_sobra_quando_exc_nao_explica_tudo`,
  `test_metadados_registram_linhas_por_tipo_para_o_funil`.

| Etapa | Valor | Saem | Motivo |
|---|---|---|---|
| Linhas lidas do CAGED (SC) | 6.782.144 | — | MOV + FOR + EXC |
| No período analisado | 6.782.144 | 0 | fora do período |
| Movimentações válidas | 6.771.692 | 10.452 | exclusões declaradas (EXC) e as declarações que elas anulam |
| Movimentações da indústria (B–F) | 2.282.348 | 4.489.344 | outras seções |

---

## BUG-03 · Frase fixa sobre dezembro

- `narrativa.legenda_serie` só acrescenta "Dezembro concentra desligamentos
  sazonais" quando o pior mês da série é dezembro e tem saldo negativo.
- Testes com o pior mês em dezembro e fora dele (casos Araranguá/Veículos e
  Itajaí/Veículos).

| Recorte | Antes | Depois |
|---|---|---|
| Itajaí (micro) · Veículos | "…pior: out/25 (saldo −204). Dezembro concentra…" | "…pior: out/25 (saldo −204)." |
| SC · indústria | "…pior: dez/25 (saldo −27.379). Dezembro concentra…" | igual (a frase vale) |

---

## BUG-04 · Formatação monetária

- Novo formatador único `comum.fmt_brl_escala` (mil / mi / bi, uma casa
  decimal, sinal tipográfico). Ele escolhe a maior escala em que o valor fica
  ≥ 1 e nunca mostra "1.000,0 mi". Usado no custo de reposição de "O que
  fazer", o único valor em escala do painel (busca por `1e6`/`mi`).
- Testes em todas as faixas, mais `test_nenhum_valor_de_bilhao_aparece_em_mi`.

| Indicador (recorte padrão, 3 salários) | Antes | Depois |
|---|---|---|
| Custo estimado de reposição | R$ 2.174,6 mi | R$ 2,2 bi |

---

## BUG-05 · Plural errado ("Mesorregiãos")

- `comum.PLURAL_NIVEL` (público) e `comum.plural_nivel(nivel, maiuscula)`.
  A Ficha passa a mostrar "Mesorregiões / Microrregiões / Municípios com
  população parecida".
- O teste `test_nenhum_plural_montado_com_s_nas_paginas` varre `dashboard/`
  atrás de `{…nivel…}s` e `+ "s"`: hoje, sem ocorrências.

---

## NAR-01 · Quadrantes alinhados à definição do guia

- Nova fonte única de rótulos e regras: **`dashboard/regras.py`** (quadrantes,
  causas, alavancas, limiares, guardas de amostra), reexportada por `comum`.
  `quadrante()` e as cores, classes CSS e legendas saem de `regras.QUADRANTES`.
- Mesma classificação (eixos e z-scores iguais), nomes novos:

  | Posição na matriz | Antes | Depois |
  |---|---|---|
  | cresce muito + perde a equipe | Expansão sob pressão | **Apagão: cresce, mas não retém** |
  | cresce muito + segura a equipe | Expansão saudável | **Expansão acelerada** |
  | cresce pouco + perde a equipe | Apagão (rotatividade crônica) | **Retração com rotatividade** |
  | cresce pouco + segura a equipe | Estagnação | **Estagnação** |

- **Lógica ajustada, não só o texto:** o filtro de alerta usa
  `QUADRANTES_ALERTA` (os que perdem a equipe). A regra de mobilidade, que
  disparava em "Expansão sob pressão", agora dispara no novo Apagão (a mesma
  posição). As cores seguem a gravidade: Apagão em vermelho, Retração em laranja.
- Atualizados: matriz e legenda, cartões de alerta (CSS `rx-alerta-retracao`),
  contagens ("X grupos em…", `narrativa.contagem_quadrantes`), modo
  apresentação, Metodologia (definição dos 4 quadrantes) e o CSV de
  diagnóstico (coluna `quadrante`).
- Testes: `test_quadrantes` (mapeamento do guia),
  `test_rotulos_dos_quadrantes_seguem_o_guia`,
  `test_rotulos_antigos_nao_aparecem_no_codigo` (busca vazia em `dashboard/`
  e `src/`) e `test_contagem_por_quadrante_bate_com_a_matriz`.

Contagens no recorte padrão (mesorregião × setor, 82 grupos):

| Quadrante novo | Grupos | Nome antigo do mesmo grupo |
|---|---|---|
| Apagão: cresce, mas não retém | 26 | Expansão sob pressão |
| Retração com rotatividade | 25 | Apagão (rotatividade crônica) |
| Expansão acelerada | 17 | Expansão saudável |
| Estagnação | 14 | Estagnação |

Mesorregião × macrofamília (66 grupos): Apagão 19 · Retração 15 · Expansão 11 · Estagnação 21.

---

## NAR-03 · Transformação como escopo de abertura; construção à parte

- Escopo novo **"Indústria de transformação (C)"**, padrão de abertura
  (`regras.ESCOPO_PADRAO`). "Indústria (B–F)" e "Toda a economia" continuam
  disponíveis. Uma só `comum.mascara_escopo` serve para agregado, perfil e
  barra lateral (substitui os `if escopo == ESCOPO_INDUSTRIA` espalhados).
- **Quem precisa de atenção:** quando o escopo inclui a seção F, os alertas
  aparecem em duas listas: "Transformação (e demais seções)" e "Construção
  (rotatividade estrutural de obra)". Um grupo conta como construção se tiver
  ≥ 50% das movimentações na seção F (`regras.FRACAO_CONSTRUCAO`). Isso vale
  por setor e por macrofamília. A tabela ganha a coluna "Grupo".
- **Panorama:** "Maior tensão" é o grupo mais tenso **da transformação**.
  Com a seção F no recorte, entra uma linha à parte para a construção, com o
  aviso de estrutural (o mesmo vale para os achados).
- Os z-scores são calculados dentro do escopo, então o grupo mais tenso muda
  com ele.
- Testes: `test_escopo_padrao_e_transformacao`, `test_filtro_de_escopo`,
  `test_maior_tensao_e_da_transformacao_e_construcao_vem_a_parte`,
  `test_marcar_secao_por_fracao_das_movimentacoes`.

| Indicador na abertura do painel | Antes (Indústria B–F) | Depois (Transformação C) |
|---|---|---|
| Movimentações | 1.139.762 | 835.950 |
| Saldo | 2.726 | 1.072 |
| Saída voluntária | 47,7% | 50,9% |
| Rotatividade descontada | 32,3% | 27,4% |
| Salário de quem entra vs quem saiu | 6% abaixo | 7% abaixo |
| Maior tensão | Construção – Vale do Itajaí (antes, sem separação) | Metalurgia e produtos de metal – Sul Catarinense |
| Expansão mais acelerada | Veículos – Vale do Itajaí (saldo 2.530) | igual (ver TAX-01) |
| Grupos analisados (meso × setor) | 82 | 59 |
| Apagão / Retração / Expansão / Estagnação | 26 / 25 / 17 / 14 | 15 / 17 / 15 / 12 |

No escopo B–F, a maior tensão fora da construção é Têxtil, confecção e
calçados – Sul Catarinense, e a da construção é Construção – Vale do Itajaí.

---

## ANA-01 · Viés de tempo de casa na causa "Salarial"

- **Regra nova (P0, sem reprocessar):** a causa *Salarial* acende quando a
  razão salário de entrada ÷ salário de saída do grupo fica **≥ 3 p.p. abaixo
  da razão do estado inteiro** no mesmo escopo e período
  (`regras.salario_pior_que_estado`, `MARGEM_SALARIAL_RELATIVA = 0,03`). Antes,
  o corte era absoluto: < 0,95.
- **Retenção, por coerência:** saída voluntária ≥ estado + 5 p.p. **com salário
  de entrada não pior que o do estado** (`regras.salario_nao_explica`). Antes
  exigia gap ≥ 1, o que quase nunca acontece (0 grupos).
- A alavanca "Revisar faixas salariais" e a "Retenção não salarial" usam as
  mesmas funções.
- **Referência = estado** (`Contexto.ref`: mesmo escopo e período, sem os
  filtros de território, setor etc.) em causas e recomendações. Antes, com
  um território filtrado, o grupo era comparado com o próprio recorte.
- **Na tela:** a coluna "Mesma razão no estado" aparece nas tabelas de causa
  (Quem precisa de atenção e Por que acontece), a frase do cartão mostra "(no
  estado, 93%)" e a legenda das causas é gerada dos limiares
  (`narrativa.legenda_causas`). A Metodologia explica o viés e a correção.
- **P1 (dentro da mesma CBO):** fica para o Lote D, porque precisa de CBO no
  agregado, ou seja, de reprocessamento.
- Testes: `test_salarial_e_relativo_ao_estado` (incluindo a borda exata de
  3 p.p.), `test_retencao_quando_salario_nao_e_pior_que_o_do_estado`,
  `test_legenda_das_causas_mostra_a_regra_e_a_referencia`.

| Indicador (12 meses) | Antes | Depois |
|---|---|---|
| Razão salarial do estado, indústria B–F | 0,940 | (referência) |
| Razão salarial do estado, transformação C | 0,929 | (referência) |
| Grupos com causa Salarial, B–F (meso × setor) | **55 / 82** | **16 / 82** |
| Grupos com causa Retenção, B–F | 0 / 82 | 4 / 82 |
| Grupos com causa Salarial, transformação | 43 / 59 | 6 / 59 |
| Grupos com causa Retenção, transformação | 0 / 59 | 2 / 59 |
| Recomendações "Revisar faixas salariais", B–F (meso × macrofamília) | 11 | 1 |
| Recomendações "Retenção não salarial", B–F | 0 | 11 |
| Recomendações "Revisar faixas salariais", transformação | 6 | 1 |
| Recomendações "Retenção não salarial", transformação | 0 | 6 |

---

## TAX-01 · "Veículos – Vale do Itajaí": autopeças e construção naval

**A hipótese se confirmou só em parte.** Abrindo o setor nos microdados
(`scripts/veiculos_por_divisao.py` → `data_processed/veiculos_por_divisao.csv`),
12 meses, Vale do Itajaí:

| Divisão CNAE | Saldo | Onde | Subclasse que puxa |
|---|---|---|---|
| 29 · Veículos automotores e autopeças | **1.602 (63%)** | Navegantes (+1.642; os demais somam negativo) | 2945-0/00 material elétrico/eletrônico para veículos (+1.604) |
| 30 · Construção naval e outros equipamentos de transporte | **928 (37%)** | Navegantes (+625), Itajaí (+334) | 3011-3/01 (+734), 3011-3/02 (+154), 3012-1/00 (+83) |
| Total (o antigo "Veículos") | 2.530 | | |

O pico de jul/26 na microrregião de Itajaí (+1.131) se divide em +942 da
divisão 29 e +189 da naval. **O motor principal da "expansão de Veículos" é
uma planta de autopeças elétricas em Navegantes, não os estaleiros.** Os
estaleiros existem e respondem por 37% do saldo.

**O que mudou:**
- `src/mapeamentos.py`: as divisões 29 e 30 viram setores distintos. O
  pipeline foi **reprocessado de ponta a ponta** (CAGED de 24 meses do FTP do
  MTE e RAIS 2025), com metadados de commit `5432643`. Conferência: todos os
  totais (admissões, desligamentos, a pedido, descontados, contagens de
  salário e escolaridade, estoque e desligados da RAIS) ficaram **idênticos**,
  e "Veículos" (35.776 admissões) = 26.383 (div. 29) + 9.393 (div. 30).
- Os achados de expansão citam o setor correto e trazem a **concentração por
  município calculada** ("100% do saldo vem de Navegantes"). Novo achado,
  "Expansão puxada por encomendas", para a construção naval do Vale do Itajaí
  (saldo 928, emprego +17,5%, quadrante **Apagão: cresce, mas não retém**),
  com nota de contexto e fontes na tela: Click Petróleo e Gás (Programa Mar
  Aberto, anúncio de 26/06/2026, Detroit Brasil e Navship) e NSC Total
  (contratos de 12/12/2024). As **fragatas da Marinha / Estaleiro Brasil Sul
  não aparecem nessas fontes e ficaram fora.**
- Metodologia: tabela "Setores: divisão CNAE → setor" gerada do mapeamento.
- `por_tipo` dos metadados preenchido (BUG-02 conferido: EXC = 5.226).
- O limite de achados passou de 5 para 6, para que "Maior tensão" nunca saia.
- Testes: `test_divisoes_29_e_30_sao_setores_distintos`,
  `test_metodologia_documenta_o_mapeamento_cnae`,
  `test_nota_de_expansao_cita_concentracao_e_fonte_do_setor_naval`,
  `test_achado_de_expansao_por_encomenda_do_setor_naval`.

| Indicador (abertura do painel) | Antes | Depois |
|---|---|---|
| Expansão mais acelerada | Veículos – Vale do Itajaí, saldo 2.530, +19,3% no ano | Veículos automotores e autopeças – Vale do Itajaí, saldo 1.602, +20,7% no ano (100% Navegantes) |
| Construção naval – Vale do Itajaí | (dentro de "Veículos") | saldo 928, +17,5% no ano, Apagão: cresce, mas não retém |
| Grupos meso × setor, transformação | 59 | 63 |
| Apagão / Retração / Expansão / Estagnação (transformação) | 15 / 17 / 15 / 12 | 13 / 20 / 14 / 16 |
| Grupos meso × setor, B–F | 82 | 86 |

---

## Lote A · números finais (após TAX-01 reprocessado)

Abertura do painel: Indústria de transformação (C), set/25–ago/26.

| Número do pitch | Versão publicada (B–F, "Veículos") | Agora (transformação, setores 29/30) |
|---|---|---|
| Movimentações | 1.139.762 | 835.950 |
| Saldo | 2.726 | 1.072 |
| Saída voluntária | 47,7% | 50,9% |
| Salário de quem entra vs quem saiu | 6% abaixo | 7% abaixo |
| Maior tensão | Construção – Vale do Itajaí | Metalurgia e produtos de metal – Sul Catarinense (construção à parte) |
| Expansão mais acelerada | Veículos – Vale do Itajaí, saldo 2.530 | Veículos automotores e autopeças – Vale do Itajaí, saldo 1.602 (100% Navegantes) |
| Construção naval – Vale do Itajaí | — | saldo 928, Apagão: cresce, mas não retém |
| Grupos com causa Salarial | 55 / 82 | 8 / 63 (B–F: 16 / 86) |
| Grupos com causa Retenção | 0 / 82 | 3 / 63 (B–F: 5 / 86) |
| Apagão / Retração / Expansão / Estagnação | (nomes antigos) | 13 / 20 / 14 / 16 |
| Custo de reposição (3 salários) | R$ 2.174,6 mi | R$ 1,7 bi (transformação); R$ 2,2 bi em B–F |
| Gap de escolaridade, Alimentos e bebidas | −0,73 | −0,73 (real; Oeste) |

---

## REC-01 · Alavanca "Formação profissional direcionada"

- **Pipeline:** nova tabela `caged_cbo.parquet` (`agregador.agregar_cbo`):
  mesorregião × seção × setor × macrofamília × nível × **CBO** × mês, com as
  mesmas colunas aditivas e a mesma `preparar_base` do agregado (fecha
  exatamente: 3.443.428 admissões, 3.328.264 desligamentos). Ela entra no
  upload do notebook e é lida pelo painel da mesma origem do agregado (Blob
  ou local). Se faltar, o painel segue sem a lista de CBOs e avisa.
- **Regra** (`regras.py`, documentada na Metodologia em "Regras das
  recomendações"): grupo mesorregião × macrofamília **industrial** em Apagão
  ou Expansão acelerada, com nível-alvo Qualificado ou Técnico e ao menos um
  sinal:
  1. gap de escolaridade < −0,05;
  2. desligamento precoce acima do estado;
  3. Técnico + Superior ≥ 1 p.p. menos frequentes entre os admitidos do que
     entre os desligados.

  Limiares de materialidade: o plano pedia "gap < 0", mas −0,03 é ruído.
  Ficam fora Administrativo e comercial e Serviços de apoio, porque não
  cabe "aprendizagem industrial" para vendedor de varejo.
- **Ação gerada** (sem nomes de curso inventados): "Turmas de
  qualificação/aprendizagem industrial para *as 5 CBOs de maior volume do
  grupo (descrição + código)* na mesorregião *X*". Na tela, aparece no cartão
  da alavanca ("O que formar") e nas colunas "Ação" e "O que formar" da
  tabela e do CSV.
- Substitui a regra antiga de formação, que disparava 1 caso (gap ≤ −0,10 em
  família técnica).
- Testes: `test_tabela_por_cbo_fecha_com_o_agregado`,
  `test_formacao_lista_as_cbos_de_maior_volume_com_descricao`,
  `test_formacao_nao_dispara_fora_do_nivel_alvo`,
  `test_formacao_nao_dispara_sem_sinal_de_falta_de_qualificacao`.

| Recorte | Formação: antes | Formação: depois | Total de recomendações |
|---|---|---|---|
| Transformação | 1 | **7** | 18 → 24 |
| Indústria B–F | 0 | **6** | 25 → 31 |

Exemplo (maior prioridade): **Alimentos e bebidas – Oeste Catarinense**
(Apagão; gap de escolaridade −0,95) → formar Magarefe (848520), Trabalhador
de tratamento do leite (841505), Desossador (848515), Salsicheiro (848115) e
Supervisor de produção da indústria alimentícia (840105).

---

## REC-02 · Recomendações com responsável, prazo e meta

- `regras.py`: `QUEM_AGE` (Empresa / Federação–SENAI / Empresa + Poder
  público), `HORIZONTE` (0–3 / 3–12 / 12+ meses) e `KPI_ALAVANCA` (KPIs
  candidatos de cada alavanca), com `FRACAO_META_DISTANCIA = 0,5` e
  `PRAZO_META_MESES = 12`.
- `comum.meta_kpi`: escolhe o candidato em que o grupo está **mais longe do
  estado, para pior** (o sinal que disparou a recomendação) e propõe andar
  metade da distância em 12 meses. Ex.: "saída voluntária do grupo: 64,0% →
  57,5% em 12 meses (estado: 50,9%)". Se o grupo já está melhor em todos, a
  meta é "manter".
- `Recomendacao` ganha `quem_age`, `horizonte` e `kpi`. Na tabela, no CSV e
  na ficha da mesorregião, entram as colunas "Quem age", "Horizonte" e "KPI
  e meta". A ficha também traz a "Ação" quando há uma.
- Testes: `test_toda_alavanca_tem_responsavel_horizonte_e_kpi`,
  `test_meta_e_metade_da_distancia_ate_o_estado`,
  `test_meta_usa_o_candidato_mais_distante_do_estado`,
  `test_recomendacoes_e_csv_trazem_as_tres_colunas`.

| Alavanca | Quem age | Horizonte | KPI (exemplo do recorte padrão) |
|---|---|---|---|
| Formação profissional direcionada | Federação–SENAI | 3–12 meses | escolaridade de quem entra vs quem saiu (Alimentos – Oeste): −0,95 → −0,51 |
| Retenção não salarial | Empresa | 0–3 meses | saída voluntária (Alimentos – Oeste): 64,0% → 57,5% |
| Revisar faixas salariais | Empresa | 0–3 meses | salário de quem entra vs quem saiu: 17% abaixo → 12% abaixo |
| Recrutamento inter-regional | Empresa + Poder público | 3–12 meses | saída voluntária / rotatividade, o que estiver pior |
| Automação e redesenho | Empresa | 12+ meses | rotatividade descontada |

---

## REC-03 · "Recrutamento inter-regional" → "Atração de talentos de outras regiões"

- **Antes:** a regra disparava num grupo em expansão quando a mesma
  macrofamília tinha saldo negativo em qualquer outra mesorregião, e a tela
  dizia "a mesma profissão sobra numa região e falta em outra". O CAGED não
  mede sobra de mão de obra.
- **Regra explícita** (`regras.REGRA_ALAVANCA`, na Metodologia):
  - **destino:** grupo em Apagão (cresce e não retém) com saldo > 0;
  - **origem:** a mesma macrofamília **e o mesmo nível**, em outra
    mesorregião, com saldo < 0 **e saída voluntária abaixo da do estado**.
    A origem fecha vagas por dispensa, não por pedido de saída: indica onde
    há gente da mesma ocupação sendo dispensada.
- **Nome honesto:** "Atração de talentos de outras regiões". A frase sobre
  "sobra" saiu. A tela mostra os **pares origem → destino**, e a evidência
  traz os números dos dois lados. Ação: "Atrair profissionais de X (nível Y)
  de A para B".
- Testes: `test_atracao_exige_mesmo_nivel_na_origem`,
  `test_atracao_exige_origem_com_saida_voluntaria_abaixo_do_estado`,
  `test_atracao_mostra_o_par_e_nao_fala_em_sobra`.

| Recorte | Antes | Depois |
|---|---|---|
| Transformação | 9 recomendações | 5 (com par) |
| Indústria B–F | 12 | 8 |

Pares no recorte padrão (exemplos): Vale do Itajaí → Oeste Catarinense
(Alimentos e bebidas, Qualificado: lá −332 com 43,8% a pedido; aqui +2.389)
e Sul Catarinense → Vale do Itajaí (Metalmecânica, Qualificado: lá −783 com
42,8% a pedido; aqui +138).
