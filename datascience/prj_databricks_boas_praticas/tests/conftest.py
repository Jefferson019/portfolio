"""Fixtures compartilhadas do pytest.

Estratégia em camadas (recomendada pela comunidade Databricks):
  1. Testes de Python puro (config, regras) → sem Spark, rodam em milissegundos.
  2. Testes de transformação → Spark local (pyspark) OU Databricks Connect.

Se `databricks-connect` estiver instalado e configurado (perfil no
~/.databrickscfg ou variáveis DATABRICKS_HOST/...), os testes rodam no
serverless do workspace — Spark, Delta e Unity Catalog reais. Caso
contrário, caem para um SparkSession local.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _spark_remoto():
    from databricks.connect import DatabricksSession  # type: ignore[import-not-found]

    builder = DatabricksSession.builder
    if os.getenv("DATABRICKS_SERVERLESS_COMPUTE_ID") or not os.getenv("DATABRICKS_CLUSTER_ID"):
        builder = builder.serverless(True)
    return builder.getOrCreate()


def _spark_local():
    from pyspark.sql import SparkSession

    return (
        SparkSession.builder.master("local[2]")
        .appName("contas_medicas-tests")
        .config("spark.sql.shuffle.partitions", "2")  # rápido em amostras pequenas
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "America/Sao_Paulo")
        .getOrCreate()
    )


@pytest.fixture(scope="session")
def spark():
    """Uma única sessão para toda a suíte (criar sessões é caro)."""
    pytest.importorskip("pyspark")
    try:
        session = _spark_remoto()
    except ImportError:
        session = _spark_local()
    yield session


@pytest.fixture(scope="session")
def contas_amostra(spark):
    """Amostra sintética que INCLUI registros ruins de propósito."""
    return spark.read.option("header", "true").csv(str(FIXTURES / "contas_medicas_amostra.csv"))
