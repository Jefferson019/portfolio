"""SILVER — limpeza, qualidade e CDC declarativo.

Boas práticas:
  - Lógica de limpeza importada do pacote testado (contas_medicas.transformations)
  - Expectativas definidas como dados (contas_medicas.quality) e aplicadas
    com expect_all_or_drop → métricas no event log
  - Linhas reprovadas vão para QUARENTENA em vez de sumirem
  - AUTO CDC (create_auto_cdc_flow) em vez de MERGE imperativo: trata
    ordenação, duplicidade e eventos fora de ordem
  - Liquid clustering em vez de particionamento/Z-ORDER
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from contas_medicas.quality import REGRAS_ALERTA, REGRAS_SILVER, expressao_quarentena
from contas_medicas.transformations import limpar_contas


@dp.temporary_view(comment="Contas tipadas e normalizadas, antes da validação.")
def contas_limpas():
    return limpar_contas(spark.readStream.table("bronze_contas"))  # noqa: F821


@dp.temporary_view(comment="Somente contas aprovadas nas regras de qualidade.")
@dp.expect_all_or_drop(REGRAS_SILVER)
@dp.expect_all(REGRAS_ALERTA)
def contas_validas():
    return spark.readStream.table("contas_limpas")  # noqa: F821


@dp.table(
    name="quarentena_contas",
    comment="Contas reprovadas em ao menos uma regra de qualidade, para análise.",
    table_properties={"quality": "quarantine"},
)
def quarentena_contas():
    return (
        spark.readStream.table("contas_limpas")  # noqa: F821
        .filter(expressao_quarentena(REGRAS_SILVER))
        .withColumn("_quarentenado_em", F.current_timestamp())
    )


# Tabela alvo do CDC: SCD tipo 1 (última versão de cada conta)
dp.create_streaming_table(
    name="silver_contas",
    comment="Contas médicas válidas, uma linha por id_conta (última versão).",
    table_properties={"quality": "silver"},
    cluster_by=["data_atendimento", "cnpj_prestador"],
)

dp.create_auto_cdc_flow(
    target="silver_contas",
    source="contas_validas",
    keys=["id_conta"],
    sequence_by=F.col("atualizado_em"),
    stored_as_scd_type=1,
    except_column_list=["_rescued_data"],
)
