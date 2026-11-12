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
