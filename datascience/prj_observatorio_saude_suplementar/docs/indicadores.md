# Dicionário de indicadores

Tabelas em `dados/ouro/` (CSV e, se o `pyarrow` estiver instalado, Parquet):

- `operadoras_indicadores` — uma linha por **operadora × período × janela**;
- `mercado_indicadores` — uma linha por **período × janela × recorte** (setor, segmento, modalidade, porte);
- `conciliacao_ans.csv` — conferência com números oficiais;
- `relatorio_qualidade.json` — diagnóstico da execução.

Valores monetários em reais (R$). Razões como fração (0,82 = 82%).

## Chaves

| Coluna | Descrição |
|---|---|
| `reg_ans` | Registro da operadora na ANS (6 dígitos) |
| `ano`, `tri`, `periodo` | Trimestre de referência (`periodo` no formato `2026T2`) |
| `janela` | `acumulado_ano`, `trimestre` ou `12_meses` |
| `recorte`, `valor` | (mercado) `setor/todos`, `segmento/<segmento>`, `modalidade/<modalidade>`, `porte_mh/<porte>` |

## Receitas e despesas (fluxos na janela)

| Coluna | Definição | Conta (plano atual) |
|---|---|---|
| `receita_contraprestacoes` | Contraprestações efetivas de planos de saúde (mensalidades) | 31 |
| `tributos_diretos_operacoes` | (-) Tributos diretos de operações com planos (negativo) | 32 |
| `outras_receitas_operacionais` | Outras receitas operacionais | 33 |
| `tributos_diretos_outras` | (-) Tributos diretos de outras atividades (negativo) | 34 |
| `receitas_financeiras` / `despesas_financeiras` | Receitas e despesas financeiras | 35 / 45 |
| `receitas_patrimoniais` / `despesas_patrimoniais` | Receitas e despesas patrimoniais | 36 / 47 |
| `despesa_assistencial` | Eventos indenizáveis líquidos / sinistros retidos | 41 |
| `despesa_comercializacao` | Despesas de comercialização | 43 |
| `outras_despesas_operacionais` | Outras despesas operacionais | 44 |
| `despesa_administrativa` | Despesas administrativas | 46 |
| `impostos_participacoes` | Impostos e participações sobre o lucro | 61 |
| `receita_total` / `despesa_total` | Soma de todos os grupos da classe 3 / classe 4 | 3x / 4x |

## Resultados

| Coluna | Fórmula |
|---|---|
| `tributos_diretos` | tributos de operações + tributos de outras atividades |
| `contraprestacoes_liquidas` | receita de contraprestações + tributos de operações |
| `resultado_operacional` | contraprestações + tributos diretos + outras receitas operacionais − assistencial − comercialização − administrativa − outras despesas operacionais |
| `resultado_financeiro` | receitas financeiras − despesas financeiras |
| `resultado_patrimonial` | receitas patrimoniais − despesas patrimoniais |
| `resultado_antes_impostos` | receita total − despesa total |
| `outros_resultados` | resultado antes de impostos − (operacional + financeiro + patrimonial) |
| `resultado_liquido` | resultado antes de impostos − impostos e participações |

## Balanço (posição no fim do trimestre)

`ativo_total`, `ativo_circulante`, `ativo_nao_circulante`, `disponivel`, `creditos_operacoes_planos`,
`realizavel_longo_prazo`, `aplicacoes_financeiras` (circulante + longo prazo), `passivo_circulante`,
`passivo_nao_circulante`, `provisoes_tecnicas` (circulante + não circulante), `patrimonio_liquido`.

## Razões

| Coluna | Fórmula | Leitura |
|---|---|---|
| `sinistralidade` | despesa assistencial ÷ contraprestações (variante adotada) | De cada R$ 1 de mensalidade, quanto foi para assistência |
| `sinistralidade_bruta` | despesa assistencial ÷ contraprestações efetivas (31) | |
| `sinistralidade_liquida` | despesa assistencial ÷ contraprestações líquidas de tributos (31 + 32) | |
| `indice_despesa_administrativa` | despesa administrativa ÷ contraprestações | |
| `indice_despesa_comercializacao` | despesa de comercialização ÷ contraprestações | |
| `indice_combinado` | (assistencial + administrativa + comercialização) ÷ contraprestações | Acima de 100%: a mensalidade não cobre essas três despesas |
| `margem_operacional` | resultado operacional ÷ contraprestações | |
| `margem_liquida` | resultado líquido ÷ receita total | Como a ANS divulga ("a cada R$ 100 de receitas…") |
| `liquidez_corrente` | ativo circulante ÷ passivo circulante | |
| `liquidez_geral` | (ativo circulante + realizável a longo prazo) ÷ (passivo circulante + não circulante) | |
| `endividamento` | (passivo circulante + não circulante) ÷ patrimônio líquido | Só com PL positivo |
| `cobertura_provisoes` | aplicações financeiras ÷ provisões técnicas | Aproximação; não é o cálculo regulatório de ativos garantidores |
| `roe` | resultado líquido em 12 meses ÷ patrimônio líquido | Só na janela de 12 meses |
| `pmcr_dias` | créditos de operações com planos ÷ contraprestações em 12 meses × 360 | Prazo médio de recebimento |
| `receita_por_beneficiario_mes` | contraprestações em 12 meses ÷ beneficiários médios ÷ 12 | Mensalidade média |
| `despesa_assistencial_por_beneficiario_mes` | despesa assistencial em 12 meses ÷ beneficiários médios ÷ 12 | Custo assistencial per capita |

Razões ficam vazias quando o denominador é zero, negativo ou ausente.

## Cadastro e qualidade (por operadora)

| Coluna | Descrição |
|---|---|
| `nome`, `razao_social`, `cnpj`, `uf`, `cidade` | Do CADOP |
| `modalidade`, `segmento` | Modalidade padronizada e segmento (médico-hospitalar, odontológico, administradora) |
| `situacao` | `ativa`, `cancelada` ou `desconhecida` (fora do cadastro) |
| `benef_medico`, `benef_odonto` | Beneficiários no fim do trimestre (quando o mês foi processado) |
| `beneficiarios` | Beneficiários do segmento da operadora no fim do trimestre |
| `beneficiarios_medios` | Média dos fins de trimestre da janela de 12 meses |
| `porte` | `pequeno`, `medio`, `grande`, `sem_beneficiarios`, `sem_informacao` ou `nao_se_aplica` |
| `amostra_valida` | Receita de contraprestações ≥ R$ 1 milhão na janela e segmento assistencial |
| `sinistralidade_atipica` | Sinistralidade fora do intervalo de 20% a 200% |

## Mercado (colunas adicionais)

| Coluna | Descrição |
|---|---|
| `n_operadoras` | Operadoras com dados completos na janela |
| `pct_resultado_liquido_positivo`, `n_resultado_liquido_positivo` | Operadoras com lucro |
| `pct_resultado_operacional_negativo` | Operadoras com prejuízo operacional (entre as que têm receita) |
| `sinistralidade_p25`, `sinistralidade_mediana`, `sinistralidade_p75` | Distribuição entre operadoras (amostra válida) |
| `hhi` | Índice Herfindahl-Hirschman pela receita de contraprestações (0 a 10.000) |
| `cr5`, `cr10` | Participação das 5 e das 10 maiores na receita |
