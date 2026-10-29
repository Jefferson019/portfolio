# dados/

| Pasta | Conteúdo | No Git? |
|---|---|---|
| `bronze/` | Arquivos originais baixados do portal da ANS (com cache) | não |
| `prata/` | Contas de interesse por trimestre, já padronizadas; cadastro de operadoras | não |
| `ouro/` | Indicadores por operadora e de mercado, conferência com a ANS e relatório de qualidade | não |
| `historico/` | Agregados pequenos de beneficiários, acumulados mês a mês | **sim** |

Tudo, exceto `historico/`, é recriado por `python -m observatorio_ans`.
