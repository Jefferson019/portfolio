"""Testes das transformações Spark.

Usam `assertDataFrameEqual` / `assertSchemaEqual` (Spark 3.5+ / DBR 14.2+),
que comparam DataFrames sem precisar de collect() manual.
"""

from datetime import date
from decimal import Decimal

import pytest

pytest.importorskip("pyspark")

from pyspark.sql import functions as F  # noqa: E402
from pyspark.testing.utils import assertDataFrameEqual  # noqa: E402

from contas_medicas.quality import REGRAS_SILVER, expressao_quarentena  # noqa: E402
from contas_medicas.transformations import (  # noqa: E402
    calcular_glosa,
    deduplicar_ultima_versao,
    limpar_contas,
    padronizar_colunas,
    resumo_mensal_prestador,
)


def test_padronizar_colunas(spark):
    df = spark.createDataFrame([(1, 2)], ["Valor Pago", "Código-TUSS"])
    assert padronizar_colunas(df).columns == ["valor_pago", "codigo_tuss"]


def test_limpar_contas_tipos_e_normalizacao(contas_amostra):
    df = limpar_contas(contas_amostra)
    linha = df.filter("id_conta = 'C003'").first()

    assert linha.tipo_guia == "INTERNACAO"  # "Internação" → domínio padronizado
    assert linha.carteirinha == "000323456789"  # só dígitos
    assert linha.valor_apresentado == Decimal("12500.00")
    assert linha.data_atendimento == date(2026, 8, 15)


def test_carteirinha_vazia_vira_null(contas_amostra):
    linha = limpar_contas(contas_amostra).filter("id_conta = 'C004'").first()
    assert linha.carteirinha is None


def test_deduplicar_mantem_versao_mais_recente(contas_amostra):
    df = deduplicar_ultima_versao(limpar_contas(contas_amostra), "id_conta", "atualizado_em")
    c002 = df.filter("id_conta = 'C002'").collect()
    assert len(c002) == 1
    assert c002[0].valor_pago == Decimal("300.00")


def test_calcular_glosa(spark):
    df = spark.createDataFrame(
        [(Decimal("200.00"), Decimal("150.00"))],
        "valor_apresentado decimal(18,2), valor_pago decimal(18,2)",
    )
    resultado = calcular_glosa(df).select("valor_glosa", F.col("pct_glosa").cast("double").alias("pct_glosa"))
    esperado = spark.createDataFrame([(Decimal("50.00"), 0.25)], "valor_glosa decimal(18,2), pct_glosa double")
    assertDataFrameEqual(resultado, esperado)


def test_regras_de_qualidade_separam_bons_e_ruins(contas_amostra):
    """As MESMAS regras do pipeline, testadas sobre dados ruins de propósito."""
    limpas = deduplicar_ultima_versao(limpar_contas(contas_amostra), "id_conta", "atualizado_em")
    ruins = {r.id_conta for r in limpas.filter(expressao_quarentena(REGRAS_SILVER)).collect()}

    # C004 sem carteirinha, C005 tipo de guia inválido,
    # C006 pago > apresentado, C007 valor zerado
    assert ruins == {"C004", "C005", "C006", "C007"}


def test_resumo_mensal_prestador(contas_amostra):
    limpas = deduplicar_ultima_versao(limpar_contas(contas_amostra), "id_conta", "atualizado_em")
    validas = limpas.filter(f"NOT ({expressao_quarentena(REGRAS_SILVER)})")
    resumo = resumo_mensal_prestador(validas)

    ago_p1 = resumo.filter("cnpj_prestador = '11111111000101' AND competencia = '2026-08-01'").first()
    assert ago_p1.qtd_contas == 2  # C001 + C002 (deduplicada)
    assert ago_p1.valor_glosa == Decimal("20.50")
