# Metodologia

Este documento descreve, passo a passo, como os arquivos brutos da ANS viram os indicadores do painel. A ideia é
que qualquer pessoa consiga auditar (e reproduzir) cada número.

## 1. Fontes

Todos os dados vêm do [Portal de Dados Abertos da ANS](https://dadosabertos.ans.gov.br/FTP/PDA/):

| Conjunto | Caminho no portal | Uso |
|---|---|---|
| Demonstrações contábeis (DIOPS) | `demonstracoes_contabeis/AAAA/nTAAAA.zip` | Receitas, despesas e balanço por operadora e trimestre |
| Operadoras ativas (CADOP) | `operadoras_de_plano_de_saude_ativas/Relatorio_cadop.csv` | Nome, modalidade, UF |
| Operadoras canceladas | `operadoras_de_plano_de_saude_canceladas/Relatorio_cadop_canceladas.csv` | Modalidade de quem já saiu do mercado (séries históricas) |
| Informações consolidadas de beneficiários (SIB) | `informacoes_consolidadas_de_beneficiarios-*/AAAAMM/*.zip` | Beneficiários por operadora, cobertura, contratação e UF |

Os nomes de pastas e arquivos são **descobertos lendo os índices do portal** (e não fixados no código), porque a
ANS já renomeou pastas (por exemplo, a de beneficiários ganhou o sufixo `-024`).

## 2. Camadas

- **bronze** — os arquivos originais, como baixados (com cache: só baixa de novo o que mudou no servidor).
- **prata** — para cada trimestre, só as contas usadas nos indicadores (até 3 dígitos, mais alguns subgrupos), com
  tipos corrigidos: registro ANS com 6 dígitos, valores no padrão brasileiro convertidos, duplicatas removidas.
- **ouro** — conceitos contábeis por operadora, janelas de tempo, indicadores por operadora e agregados de mercado.

## 3. Leitura dos arquivos contábeis

Cada zip trimestral traz um CSV com as colunas `DATA`, `REG_ANS`, `CD_CONTA_CONTABIL`, `DESCRICAO`,
`VL_SALDO_INICIAL` e `VL_SALDO_FINAL`. O leitor:

- detecta o encoding (UTF-8 ou latin-1) e o separador pela amostra inicial;
- aceita apelidos de colunas (o layout já mudou; arquivos antigos não têm saldo inicial);
- converte `1.234.567,89`, `-12,5` e `(1.234,56)` em número;
- usa o trimestre do **nome do arquivo** (a coluna `DATA` muda de formato entre anos e é usada só para validação);
- remove linhas duplicadas de operadora + conta, mantendo a última.

## 4. Plano de contas → conceitos

O Plano de Contas Padrão da ANS mudou ao longo do tempo (RN 290/2012, RN 435/2018, RN 528/2022). Por isso cada
conceito é resolvido **trimestre a trimestre pela descrição da conta**, com o código padrão como alternativa:

| Conceito | Grupo (plano atual) | Palavras-chave na descrição |
|---|---|---|
| Contraprestações efetivas | 31 | CONTRAPRESTAÇÕES |
| (-) Tributos diretos de operações com planos | 32 | TRIBUTOS DIRETOS DE OPERAÇÕES |
| Outras receitas operacionais | 33 | OUTRAS RECEITAS OPERACIONAIS |
| (-) Tributos diretos de outras atividades | 34 | TRIBUTOS DIRETOS DE OUTRAS |
| Receitas financeiras | 35 (era 34) | RECEITAS FINANCEIRAS |
| Receitas patrimoniais | 36 (era 35) | RECEITAS PATRIMONIAIS |
| Eventos indenizáveis líquidos (despesa assistencial) | 41 | EVENTOS INDENIZÁVEIS / SINISTROS RETIDOS |
| Despesas de comercialização | 43 | COMERCIALIZAÇÃO |
| Outras despesas operacionais | 44 | OUTRAS DESPESAS OPERACIONAIS |
| Despesas financeiras | 45 | DESPESAS FINANCEIRAS |
| Despesas administrativas | 46 | DESPESAS ADMINISTRATIVAS |
| Despesas patrimoniais | 47 | DESPESAS PATRIMONIAIS |
| Impostos e participações sobre o lucro | 61 | IMPOSTOS E PARTICIPAÇÕES |
| Ativo / passivo circulante e não circulante, PL | 12, 13, 21, 23, 25 | pelas descrições |
| Aplicações financeiras | 122 + subgrupos de 131 | APLICAÇÕES |
| Provisões técnicas | 211 + subgrupos de 23 | PROVISÕES TÉCNICAS |

Um código padrão só é usado quando sua descrição não pertence claramente a outro conceito — é isso que impede, por
exemplo, que o antigo grupo 34 ("Receitas Financeiras") seja lido como "tributos". O mapeamento efetivo de cada
trimestre fica em `relatorio_qualidade.json` → `conceitos.<período>.resolucao`.

Além dos conceitos, o pipeline soma **todos** os grupos da classe 3 (receita total) e da classe 4 (despesa total),
para que o resultado líquido não dependa de nenhum grupo esquecido.

## 5. Convenção de sinal

A ANS não documenta se saldos credores aparecem com sinal negativo, nem se deduções aparecem em valor absoluto.
Em vez de supor, o pipeline infere a convenção **em cada trimestre**:

1. para cada classe (ativo, passivo, receitas, despesas), calcula a mediana da conta-âncora entre todas as
   operadoras (ex.: grupo 31 para receitas); mediana negativa ⇒ a classe inteira é invertida;
2. impostos sobre o lucro (classe 6) seguem a natureza das despesas;
3. grupos de dedução da receita (descrição começando por "(-)" ou "tributos diretos") são forçados a ficar negativos;
4. a convenção é **validada**: a soma dos grupos tem de bater com a linha total da classe (quando existe). A taxa de
   acerto fica em `conceitos.<período>.validacao`.

## 6. Acumulação e janelas de tempo

Os saldos de resultado (DRE) dos balancetes são acumulados no ano. O pipeline **confirma** isso ano a ano: em
balancetes acumulados, o saldo inicial do trimestre t é igual ao saldo final de t−1. Se os arquivos estivessem em
valores do trimestre, o cálculo se ajustaria (resultado em `relatorio_qualidade.json` → `acumulacao`).

Com o acumulado no ano (YTD) de cada trimestre:

- **acumulado no ano** = YTD(t) — é como a ANS divulga (ex.: "1º semestre");
- **trimestre isolado** = YTD(t) − YTD(t−1), ou YTD(1) no 1º trimestre;
- **últimos 12 meses** = YTD(t, ano) + YTD(4º tri, ano−1) − YTD(t, ano−1); no 4º trimestre, o próprio YTD.

Se faltar algum trimestre necessário para a operadora, a janela fica vazia (nada é interpolado). Itens de balanço
usam a posição no fim do trimestre.

## 7. Indicadores

As fórmulas estão em [indicadores.md](indicadores.md). Dois pontos importantes:

- **Sinistralidade.** Eventos indenizáveis líquidos ÷ contraprestações. Há duas leituras possíveis do denominador:
  contraprestações efetivas (grupo 31) ou contraprestações líquidas de tributos diretos (31 + 32). O pipeline
  calcula as duas e, no modo `auto`, adota a que tiver **menor erro médio contra as sinistralidades oficiais**
  divulgadas pela ANS. A escolha e os erros ficam no relatório de qualidade e no painel. Para fixar uma definição,
  ajuste `sinistralidade` em `projeto.toml`.
- **Razões de mercado** são calculadas sobre somas (soma das despesas ÷ soma das receitas), como a ANS faz — e não
  como média simples entre operadoras. A distribuição entre operadoras (mediana e quartis) é mostrada à parte, só
  com operadoras com receita de pelo menos R$ 1 milhão na janela e sinistralidade entre 20% e 200%.

## 8. Cadastro, segmentos e porte

- **Modalidade** vem do CADOP (ativas + canceladas, para cobrir operadoras que já saíram do mercado).
- **Segmentos**: médico-hospitalar (autogestão, cooperativa médica, filantropia, medicina de grupo, seguradora
  especializada em saúde), exclusivamente odontológico (cooperativa odontológica, odontologia de grupo) e
  administradoras de benefícios. O "setor" soma todos, como nas divulgações da ANS.
- **Porte**, pelo critério da ANS: pequeno (< 20 mil beneficiários), médio (20 a 100 mil) e grande (> 100 mil),
  usando os beneficiários médico-hospitalares (ou odontológicos, para operadoras odontológicas) no fim do
  trimestre; quando o mês não foi processado, usa a posição mais recente.

## 9. Beneficiários

Os arquivos mensais do SIB são grandes (centenas de MB por mês). O pipeline processa apenas: o mês mais recente,
os últimos fins de trimestre (padrão: 5) e o mesmo mês do ano anterior. Guarda só agregados pequenos em
`dados/historico/` (versionados no Git), e nas execuções seguintes processa apenas meses novos. Os zips são apagados
depois de agregados.

Os indicadores por beneficiário (mensalidade média e despesa assistencial por beneficiário) usam a média dos fins de
trimestre disponíveis dentro da janela de 12 meses.

## 10. Conferência com a ANS

`src/observatorio_ans/referencias/ans_divulgacoes.csv` lista números oficiais divulgados pela ANS (com período,
recorte, valor, tolerância, fonte e link). Para cada um, o pipeline recalcula o mesmo número e marca:

- **confere** — dentro da tolerância (ex.: ±1 p.p. para sinistralidade; ±10% para resultados, que são diferenças
  entre números grandes);
- **diverge** — fora da tolerância (vale investigar: critério diferente, reenvio de dados, definição);
- **sem dados** — período fora do intervalo processado.

Para acrescentar uma referência, basta adicionar uma linha ao CSV.

## 11. Limitações conhecidas

- Os dados são declarados pelas operadoras e podem ser reenviados. Um mesmo trimestre pode mudar entre execuções.
- A ANS aplica filtros de consistência próprios no seu painel (e eventuais ajustes de fatos atípicos). Diferenças
  pequenas são esperadas.
- Corresponsabilidade (intercâmbio entre operadoras) é tratada como está no plano de contas; não há eliminação de
  operações entre operadoras de um mesmo grupo econômico.
- Porte e beneficiários antes de maio/2021 usam a posição mais próxima disponível, porque a série consolidada atual
  do SIB começa nessa data.
