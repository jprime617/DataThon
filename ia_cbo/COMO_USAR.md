# Classificação dos CBOs com a IA paga (sem API)

São 2.207 CBOs divididos em 23 lotes de até 100 códigos (R5.3). Os lotes 01 a 22 têm 100 códigos cada, e o lote 23 tem 7.
Cada prompt já contém as regras, os códigos e o formato de resposta exigido.

## Passo a passo

1. Abra `prompts/lote_01.txt`, copie **tudo** e cole na IA paga. Use o modelo mais forte disponível.
2. Copie **só o JSON** da resposta e salve em `respostas/lote_01.json` (mesmo número do prompt).
3. Repita para os lotes 02 a 23. Abra uma conversa nova a cada ~5 lotes para a IA não "misturar" os lotes.
4. Confira as respostas. Rode na raiz do projeto:

   ```bash
   .venv/bin/python -c "import sys; from src.cbo_ia import _extrair_mapeamento as e; [print(f, len(e(open(f).read()))) for f in sys.argv[1:]]" ia_cbo/respostas/*.json
   ```

   Cada arquivo tem que mostrar 100 (o lote 23 mostra 7). Se aparecer 0 ou um número menor, a resposta veio cortada: peça para a IA "repetir só o JSON completo" e salve de novo.

## Formato que o sistema consome

Um objeto JSON por lote, com a chave igual ao código CBO (6 dígitos, como texto):

```json
{
  "784205": {"macrofamilia": "Operação de linha e processo", "nivel": "Básico", "justificativa": "Ocupação elementar de linha."},
  "411010": {"macrofamilia": "Administrativo e comercial", "nivel": "Qualificado", "justificativa": ""}
}
```

- `macrofamilia`: um dos 12 valores do conjunto fechado listado no prompt. Qualquer outro valor vira `Não classificado`.
- `nivel`: `Básico`, `Qualificado`, `Técnico` ou `Superior`.
- `justificativa`: obrigatória quando a família foge da sugerida ou o nível foge do `nivel_cbo`. Sem justificativa, o sistema volta para a sugestão.

O sistema tolera texto ou bloco ```json em volta, mas o arquivo precisa ter um único objeto JSON completo.
A ordem dos lotes não importa, porque o sistema junta todos pelo código.

## Depois de salvar as 23 respostas (M2.C3 e M2.C4)

5. Rode a classificação a partir dos arquivos (não precisa de chave de API) e regenere os artefatos sem publicar no Azure:

   ```bash
   export LLM_PROVIDER=arquivo LLM_MODELO_MANUAL="<nome do modelo usado no chat>" RECLASSIFICAR_CBO=1 PULAR_UPLOAD=1
   .venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/01_pipeline.ipynb
   ```

   - Se faltar algum lote, o erro lista quais. Se um arquivo estiver sem JSON válido, o erro diz qual.
   - A concordância compara a IA paga com a classificação anterior do Gemini (`data_processed/cbo_macrofamilias_gemini.csv`). A página "Que profissional falta" mostra o resultado.
   - Confira em `data_processed/cbo_macrofamilias.csv.meta.json`: `provedor` = `ClienteArquivo`, o modelo informado e `cbos_comparados` perto de 2.206.

6. **Revisão humana (M2.C4):** abra `data_processed/cbo_divergencias.csv`, que já vem ordenado por volume, e revise as 20 primeiras linhas.
   - Para corrigir um código, edite o `respostas/lote_NN.json` que o contém. Mude `macrofamilia` e/ou `nivel` e escreva uma `justificativa` começando com `Revisão humana:`.
   - Depois, rode o passo 5 de novo.

7. Faça commit de `ia_cbo/respostas/`, `data_processed/` e do notebook. Atualize o Estado do M2 no `PLANO_RETA_FINAL.md`.

> Testado em 12/11 com respostas simuladas a partir do mapeamento do Gemini: os 23 lotes foram lidos e todos os 2.206 CBOs casaram com os prompts (inclusive os de 5 dígitos, como `10105`).
