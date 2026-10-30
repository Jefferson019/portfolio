"""BRONZE — ingestão incremental com Auto Loader (cloudFiles).

Boas práticas:
  - Streaming table + Auto Loader: processa só arquivos novos, com checkpoint gerenciado
  - Origem é um Volume do Unity Catalog (nada de caminhos DBFS/montagens)
  - Colunas de linhagem (_arquivo_origem, _ingerido_em) desde a primeira camada
  - Dados que não casam com o schema vão para `_rescued_data` (nada se perde)
  - Caminho de origem parametrizado via configuração do pipeline
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from contas_medicas.transformations import padronizar_colunas

LANDING = spark.conf.get("contas_medicas.landing_path")  # noqa: F821 — `spark` é injetado pelo runtime


@dp.table(
    name="bronze_contas",
    comment="Contas médicas brutas, como recebidas da origem (append-only).",
    table_properties={"quality": "bronze"},
)
@dp.expect("arquivo_legivel", "_rescued_data IS NULL")  # só alerta (WARN): mede, não descarta
def bronze_contas():
    df = (
        spark.readStream.format("cloudFiles")  # noqa: F821
        .option("cloudFiles.format", "csv")
        .option("header", "true")
        .option("cloudFiles.inferColumnTypes", "false")  # tipagem é feita na silver
        .option("cloudFiles.schemaEvolutionMode", "rescue")
        .load(LANDING)
    )
    return padronizar_colunas(df).select(
        "*",
        F.col("_metadata.file_path").alias("_arquivo_origem"),
        F.current_timestamp().alias("_ingerido_em"),
    )
