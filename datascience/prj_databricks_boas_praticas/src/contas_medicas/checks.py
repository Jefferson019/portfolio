"""Entry point `checagens` do wheel: asserções pós-pipeline.

Roda depois do pipeline no job. Falha (exit != 0) se as tabelas gold
estiverem vazias, com schema inesperado ou com taxa de quarentena alta —
assim o problema aparece no job, e não no dashboard do usuário.
"""

from __future__ import annotations

import sys

from pyspark.sql import SparkSession

from contas_medicas.config import Ambiente, parse_args
from contas_medicas.logging_utils import get_logger

COLUNAS_GOLD = {
    "competencia",
    "cnpj_prestador",
    "qtd_contas",
    "valor_apresentado",
    "valor_pago",
    "valor_glosa",
    "pct_glosa",
}
LIMITE_QUARENTENA = 0.05  # 5%


def _spark() -> SparkSession:
    # Em jobs Databricks a sessão já existe; getOrCreate apenas a recupera.
    return SparkSession.builder.getOrCreate()


def avaliar(amb: Ambiente, spark: SparkSession) -> list[str]:
    """Devolve a lista de problemas encontrados (vazia = tudo certo)."""
    problemas: list[str] = []

    gold = spark.table(amb.tabela("gold_resumo_mensal_prestador"))
    faltando = COLUNAS_GOLD - set(gold.columns)
    if faltando:
        problemas.append(f"colunas ausentes na gold: {sorted(faltando)}")
    if gold.limit(1).count() == 0:
        problemas.append("gold_resumo_mensal_prestador está vazia")

    total = spark.table(amb.tabela("bronze_contas")).count()
    quarentena = spark.table(amb.tabela("quarentena_contas")).count()
    if total and quarentena / total > LIMITE_QUARENTENA:
        problemas.append(f"quarentena acima do limite: {quarentena}/{total} ({quarentena / total:.1%})")
    return problemas


def main(argv: list[str] | None = None) -> None:
    amb = parse_args(argv if argv is not None else sys.argv[1:])
    log = get_logger("checagens", catalog=amb.catalog, schema=amb.schema)
    problemas = avaliar(amb, _spark())
    if problemas:
        for p in problemas:
            log.error(p)
        raise SystemExit(1)
    log.info("checagens de qualidade OK")


if __name__ == "__main__":
    main()
