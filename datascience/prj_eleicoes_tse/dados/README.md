# dados/

| Pasta | Conteúdo | No Git? |
|---|---|---|
| `bronze/` | Arquivos `.zip` originais, exatamente como baixados do TSE | não — ficam no *artifact* do workflow |
| `prata/` | Tabelas extraídas e padronizadas (presidente por município/zona, comparecimento, candidaturas) | não — ficam no *artifact* do workflow |
| `resultados/` | Tabelas finais da análise (CSV) e `fontes_e_execucao.json` com URL, tamanho e SHA-256 de cada arquivo baixado | **sim** |

## Tabelas em `resultados/`

| Arquivo | Uma linha por |
|---|---|
| `presidente_brasil.csv` | ano × turno × candidato |
| `presidente_regiao.csv` / `presidente_uf.csv` | ano × turno × região/UF × candidato |
| `presidente_municipio.csv.gz` | ano × turno × município × candidato |
| `presidente_vencedor_municipio.csv.gz` | ano × turno × município (1º colocado e margem sobre o 2º) |
| `conferencia_tse.csv` | total calculado × resultado oficial divulgado pelo TSE |
| `participacao_{brasil,uf,municipio}` | aptos, comparecimento, abstenção, válidos, brancos e nulos |
| `entre_turnos_municipio.csv.gz` | % de cada finalista no 1º e 2º turno, por município |
| `comparacao_<ano>_<ano>_municipio.csv.gz` | % do partido no último turno de cada ano, por município |
| `perfil_candidaturas.csv` | ano × cargo: mulheres, pessoas negras e idade entre candidaturas e eleitos |
| `instrucao_candidaturas.csv` | ano × grau de instrução: candidaturas, eleitos e taxa de sucesso |

Percentuais em escala 0–100. Código de município = código do TSE. `ZZ` = exterior.
