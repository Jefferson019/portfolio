"""Transformações puras: DataFrame entra, DataFrame sai.

Nenhuma função aqui lê ou grava tabelas, usa `dbutils` ou depende de
widgets. Isso permite testá-las localmente (pyspark) ou via Databricks
Connect, e reutilizá-las tanto no pipeline quanto em jobs.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

TIPOS_GUIA = {
    "C": "CONSULTA",
    "CONSULTA": "CONSULTA",
    "S": "SADT",
    "SADT": "SADT",
    "I": "INTERNACAO",
    "INTERNACAO": "INTERNACAO",
    "INTERNAÇÃO": "INTERNACAO",
    "O": "ODONTO",
    "ODONTO": "ODONTO",
}


def padronizar_colunas(df: DataFrame) -> DataFrame:
    """snake_case, sem espaços nem acentos comuns nos nomes de coluna."""
    traducao = str.maketrans("áàãâéêíóôõúç", "aaaaeeiooouc")

    def _normaliza(nome: str) -> str:
        return nome.strip().lower().translate(traducao).replace(" ", "_").replace("-", "_")

    return df.toDF(*[_normaliza(c) for c in df.columns])


def limpar_contas(df: DataFrame) -> DataFrame:
    """Tipagem e normalização de uma conta médica vinda da bronze."""
    mapa_tipo = F.create_map(*[F.lit(x) for kv in TIPOS_GUIA.items() for x in kv])
    tipo_bruto = F.upper(F.trim(F.col("tipo_guia")))

    return (
        df.withColumn("id_conta", F.trim("id_conta"))
        .withColumn("carteirinha", F.regexp_replace("carteirinha", r"\D", ""))
        .withColumn("codigo_tuss", F.regexp_replace("codigo_tuss", r"\D", ""))
        .withColumn("tipo_guia", F.coalesce(mapa_tipo[tipo_bruto], tipo_bruto))
        .withColumn("data_atendimento", F.to_date("data_atendimento"))
        .withColumn("valor_apresentado", F.col("valor_apresentado").cast("decimal(18,2)"))
        .withColumn("valor_pago", F.col("valor_pago").cast("decimal(18,2)"))
        .withColumn("atualizado_em", F.to_timestamp("atualizado_em"))
        # Strings vazias viram NULL para as expectativas funcionarem
        .withColumn("carteirinha", F.when(F.col("carteirinha") == "", None).otherwise(F.col("carteirinha")))
    )


def deduplicar_ultima_versao(df: DataFrame, chave: str, ordem: str) -> DataFrame:
    """Mantém apenas o registro mais recente por chave.

    Em pipelines prefira AUTO CDC (`dp.create_auto_cdc_flow`); esta função
    serve para jobs batch e para a lógica ser testável isoladamente.
    """
    w = Window.partitionBy(chave).orderBy(F.col(ordem).desc_nulls_last())
    return df.withColumn("_rn", F.row_number().over(w)).filter("_rn = 1").drop("_rn")


def calcular_glosa(df: DataFrame) -> DataFrame:
    """Adiciona valor e percentual de glosa (apresentado − pago)."""
    return df.withColumn(
        "valor_glosa", (F.col("valor_apresentado") - F.col("valor_pago")).cast("decimal(18,2)")
    ).withColumn(
        "pct_glosa",
        F.when(F.col("valor_apresentado") > 0, F.round(F.col("valor_glosa") / F.col("valor_apresentado"), 4)),
    )


def resumo_mensal_prestador(df: DataFrame) -> DataFrame:
    """Agregado gold: produção e glosa por prestador e competência."""
    return (
        calcular_glosa(df)
        .withColumn("competencia", F.date_trunc("month", "data_atendimento").cast("date"))
        .groupBy("competencia", "cnpj_prestador")
        .agg(
            F.countDistinct("id_conta").alias("qtd_contas"),
            F.sum("valor_apresentado").alias("valor_apresentado"),
            F.sum("valor_pago").alias("valor_pago"),
            F.sum("valor_glosa").alias("valor_glosa"),
        )
        .withColumn("pct_glosa", F.round(F.col("valor_glosa") / F.col("valor_apresentado"), 4))
    )
