# PegaSUS data scaffold

Current emphasis:

- DATASUS FTP self-scanning
- DATASUS file inventory and dataset-family assembly
- generic DBF/DBC decoding
- empirical table profiling
- compact central translation grammar
- SIDRA catalog/search plus normalized values path

## Compact translation grammar

Use block-oriented directives so LLM output stays short.

```text
$ RACACOR cat raça_cor
= 1 branca
= 2 preta
= 3 amarela
= 4 parda
= 5 indigena

$ CODMUNRES mun município_residência
> ibge6

@ SIM_DO CAUSABAS code causa_básica
> cid10
```

Directive meanings:

- `$ VAR KIND LABEL...` global variable definition
- `@ SCOPE VAR KIND LABEL...` dataset-scoped override
- `= RAW LABEL...` categorical value translation
- `> RULE...` one or more transformation rules
- `~ ALIAS...` aliases/synonyms

Suggested kinds:

- `cat`, `date`, `mun`, `uf`, `num`, `txt`, `code`, `id`, `flag`, `unknown`
