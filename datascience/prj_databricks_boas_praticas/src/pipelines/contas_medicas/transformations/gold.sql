-- GOLD — materialized view agregada para consumo (BI / painéis).
-- Boas práticas:
--   * Materialized view: o motor decide entre refresh incremental ou completo
--   * Nomes sem catálogo/schema → usam o padrão do pipeline (portável entre ambientes)
--   * Liquid clustering pelas colunas mais filtradas
--   * COMMENT descrevendo o que UMA LINHA representa

CREATE OR REFRESH MATERIALIZED VIEW gold_resumo_mensal_prestador
CLUSTER BY (competencia, cnpj_prestador)
COMMENT 'Uma linha por prestador (CNPJ) e competência (mês de atendimento): produção apresentada, paga e glosada.'
TBLPROPERTIES ('quality' = 'gold')
AS
SELECT
  CAST(date_trunc('MONTH', data_atendimento) AS DATE)            AS competencia,
  cnpj_prestador,
  COUNT(DISTINCT id_conta)                                       AS qtd_contas,
  SUM(valor_apresentado)                                         AS valor_apresentado,
  SUM(valor_pago)                                                AS valor_pago,
  SUM(valor_apresentado - valor_pago)                            AS valor_glosa,
  ROUND(SUM(valor_apresentado - valor_pago) / SUM(valor_apresentado), 4) AS pct_glosa
FROM silver_contas
GROUP BY ALL;
