-- Comentários de tabela e coluna versionados como código.
-- Aplicados pelo job `contas_medicas_metadata_job` (resources/metadata.job.yml).
-- Regra: descreva o que a linha representa, unidades e valores válidos —
-- não apenas repita o nome da coluna.

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

COMMENT ON TABLE silver_contas IS
  'Uma linha por conta médica (id_conta), na versão mais recente recebida. Apenas contas aprovadas nas regras de qualidade.';

ALTER TABLE silver_contas ALTER COLUMN id_conta
  COMMENT 'Identificador único da conta médica no sistema de origem.';
ALTER TABLE silver_contas ALTER COLUMN carteirinha
  COMMENT 'Número da carteirinha do beneficiário, somente dígitos. Dado pessoal: acesso restrito.';
ALTER TABLE silver_contas ALTER COLUMN tipo_guia
  COMMENT 'Tipo de guia TISS. Valores válidos: CONSULTA, SADT, INTERNACAO, ODONTO.';
ALTER TABLE silver_contas ALTER COLUMN codigo_tuss
  COMMENT 'Código do procedimento na tabela TUSS (8 dígitos).';
ALTER TABLE silver_contas ALTER COLUMN valor_apresentado
  COMMENT 'Valor cobrado pelo prestador, em reais (BRL), sempre > 0.';
ALTER TABLE silver_contas ALTER COLUMN valor_pago
  COMMENT 'Valor efetivamente pago após auditoria, em reais (BRL). Nunca maior que o apresentado.';
ALTER TABLE silver_contas ALTER COLUMN data_atendimento
  COMMENT 'Data em que o atendimento foi realizado (não a data de envio da conta).';
