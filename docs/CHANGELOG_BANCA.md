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
  movimentações é, portanto, 2 × EXC (10.452 = 2 × 5.226). *Conferência com
  os microdados: ver a nota de verificação abaixo.*
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
