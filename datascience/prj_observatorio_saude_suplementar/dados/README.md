# dados/

| Pasta | Conteúdo | No Git? |
|---|---|---|
| `bronze/` | Arquivos originais baixados do portal da ANS (com cache) | não |
| `prata/` | Contas de interesse por trimestre, já padronizadas; cadastro de operadoras | não |
| `ouro/` | Indicadores por operadora e de mercado, conferência com a ANS e relatório de qualidade | não |
| `historico/` | Agregados pequenos de beneficiários, acumulados mês a mês | **sim** |
| `resultados/` | Conferência com os números oficiais da ANS e relatório de qualidade da última execução | **sim** |

Tudo, exceto `historico/` e `resultados/`, é recriado por `python -m observatorio_ans`. Os dois são atualizados
pelo workflow mensal e ficam no repositório para consulta direta (o GitHub mostra o CSV como tabela).
