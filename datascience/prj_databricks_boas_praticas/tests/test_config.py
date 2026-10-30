"""Testes de Python puro — não precisam de Spark."""

import pytest

from contas_medicas.config import Ambiente, parse_args
from contas_medicas.quality import REGRAS_SILVER, expressao_quarentena


def test_tabela_qualificada_tres_partes():
    amb = Ambiente(catalog="dev", schema="jefferson")
    assert amb.tabela("silver_contas") == "dev.jefferson.silver_contas"
    assert not amb.is_prod


@pytest.mark.parametrize("valor", ["prod; DROP TABLE x", "com espaço", "", "1abc"])
def test_rejeita_identificadores_invalidos(valor):
    with pytest.raises(ValueError):
        Ambiente(catalog=valor, schema="ok")


def test_parse_args_named_parameters():
    amb = parse_args(["--catalog", "prod", "--schema", "contas_medicas"])
    assert amb.is_prod
    assert amb.schema == "contas_medicas"


def test_quarentena_inverte_todas_as_regras():
    expr = expressao_quarentena(REGRAS_SILVER)
    assert expr.startswith("NOT (")
    for regra in REGRAS_SILVER.values():
        assert regra in expr


def test_quarentena_sem_regras_falha():
    with pytest.raises(ValueError):
        expressao_quarentena({})
