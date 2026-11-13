# Roadmap: o que fica para depois do datathon

Itens que o plano da banca (`PLANO_CORRECOES_DATATHON.md`) marcou como P2 ou
que ficaram de fora do Lote D, cada um com o motivo.

## Benchmark SC × Brasil (ANA-04, parte que não coube)

- **Feito no Lote D:** saída voluntária por seção, SC × Brasil, dos mesmos
  `.7z` nacionais do CAGED (`src/caged_brasil.py` →
  `data_processed/caged_brasil_secao.parquet`), com IC de 95% por bootstrap
  de municípios (`comum.benchmark_brasil`). A rotatividade da transformação
  é comparada com a taxa oficial do MTE (27,6%, out/25–set/26).
- **Falta: rotatividade do Brasil por seção.** A taxa descontada divide pelo
  estoque, e o estoque nacional por seção não está no repositório. Dois
  caminhos: as Tabelas 10 e 11 do Novo CAGED (MTE, planilha mensal, que
  publicam a rotatividade descontada por seção para o Brasil e por UF) ou a
  RAIS 2025 de todas as regiões (vários GB; hoje só a do Sul é baixada).
- **Falta: alinhar a janela.** A taxa oficial cobre out/25–set/26 e o painel
  usa set/25–ago/26. Com a planilha do MTE, dá para recortar a mesma janela.

## Incerteza (ANA-04, extensão)

- Intervalos de confiança por bootstrap (municípios) também para os
  indicadores dos grupos da matriz (saída voluntária, rotatividade, razão
  salarial) e para a contagem de grupos com cada causa: dizer quando um
  grupo está em Apagão "com folga" ou na fronteira.
- Sensibilidade dos quadrantes ao corte de amostra (`MIN_MOVIMENTACOES`).

## Estoque e séries

- RAIS 2024 para ter o estoque no início da janela e calcular o estoque
  médio de verdade (hoje, 31/12/2025 aproxima a média).
- Estoque mensal rolado (estoque de 31/12 ± saldo acumulado do CAGED).

## Classificação por IA

- **50 divergências entre as rodadas** em que o prefixo da CBO não resolve
  continuam com a 1ª rodada, à espera de revisão manual em
  `ia_cbo/overrides.csv`. Todas têm menos de 600 movimentações; as 11
  maiores já foram revisadas no TAX-03.
- Validar com a equipe os 12 overrides feitos com revisão assistida (autor
  marcado em `ia_cbo/overrides.csv`).
- Rodar `ia_cbo/classificar.py` pela API para medir a concordância chat ×
  API com o mesmo modelo e os mesmos prompts.

## Recomendações

- Automação (REC-06) virou observação: a regra só dispara de 0 a 1 vez por
  escopo. Uma regra útil precisa de dados de investimento e produtividade,
  que o CAGED não tem (ex.: PIA-Empresa do IBGE).
- Custo de reposição (REC-05): trocar a premissa do time por uma referência
  publicada, quando houver uma citável.
