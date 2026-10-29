import numpy as np
import pandas as pd
import pytest

from observatorio_ans.plano_contas import resolver_conceitos
from observatorio_ans.util import (
    detectar_encoding,
    normalizar_reg_ans,
    normalizar_texto,
    parse_valor_br,
    separar_periodo,
)


def test_parse_valor_br():
    s = pd.Series(
        ["1.234.567,89", "1234567,89", "-12,5", "1234.5", "1.234.567", "", None, " 10,00 "]
    )
    v = parse_valor_br(s)
    assert v.iloc[0] == pytest.approx(1234567.89)
    assert v.iloc[1] == pytest.approx(1234567.89)
    assert v.iloc[2] == pytest.approx(-12.5)
    assert v.iloc[3] == pytest.approx(1234.5)
    assert v.iloc[4] == pytest.approx(1234567)
    assert np.isnan(v.iloc[5]) and np.isnan(v.iloc[6])
    assert v.iloc[7] == pytest.approx(10.0)


def test_normalizar_reg_ans():
    s = normalizar_reg_ans(pd.Series(["5711", "005711", "41.976-1", "", None]))
    assert s.tolist()[:3] == ["005711", "005711", "419761"]
    assert s.isna().tolist()[3:] == [True, True]


def test_detectar_encoding():
    assert detectar_encoding("PATRIMÔNIO LÍQUIDO".encode()) == "utf-8-sig"
    assert detectar_encoding("PATRIMÔNIO LÍQUIDO".encode("latin-1")) == "latin-1"
    # amostra cortada no meio de um caractere multibyte continua sendo UTF-8
    assert detectar_encoding("AÇÃO".encode()[:-1]) == "utf-8-sig"


def test_texto_e_periodo():
    assert normalizar_texto("  Patrimônio   líquido ") == "PATRIMONIO LIQUIDO"
    assert separar_periodo("2026T2") == (2026, 2)
    with pytest.raises(ValueError):
        separar_periodo("2026-2")


def _desc(d):
    return {k: normalizar_texto(v) for k, v in d.items()}


def test_resolucao_plano_atual():
    descricoes = _desc(
        {
            "31": "CONTRAPRESTAÇÕES EFETIVAS DE PLANO DE ASSISTÊNCIA À SAÚDE",
            "32": "(-) TRIBUTOS DIRETOS DE OPERAÇÕES DE ASSISTÊNCIA À SAÚDE",
            "33": "OUTRAS RECEITAS OPERACIONAIS",
            "34": "(-) TRIBUTOS DIRETOS DE OUTRAS ATIVIDADES DE ASSISTÊNCIA À SAÚDE",
            "35": "RECEITAS FINANCEIRAS",
            "36": "RECEITAS PATRIMONIAIS",
            "41": "EVENTOS INDENIZÁVEIS LÍQUIDOS / SINISTROS RETIDOS",
            "46": "DESPESAS ADMINISTRATIVAS",
        }
    )
    r = resolver_conceitos(set(descricoes), descricoes)
    assert r.contas["receitas_financeiras"] == ["35"]
    assert r.contas["tributos_diretos_outras"] == ["34"]
    assert r.contas["receita_contraprestacoes"] == ["31"]
    assert r.origem["despesa_assistencial"] == "descricao"


def test_resolucao_plano_antigo_nao_confunde_grupo_34():
    descricoes = _desc(
        {
            "31": "CONTRAPRESTAÇÕES EFETIVAS DE PLANO DE ASSISTÊNCIA À SAÚDE",
            "33": "OUTRAS RECEITAS OPERACIONAIS",
            "34": "RECEITAS FINANCEIRAS",
            "35": "RECEITAS PATRIMONIAIS",
        }
    )
    r = resolver_conceitos(set(descricoes), descricoes)
    assert r.contas["receitas_financeiras"] == ["34"]
    assert r.contas["receitas_patrimoniais"] == ["35"]
    assert "tributos_diretos_outras" not in r.contas  # o 34 não pode virar "tributos"


def test_resolucao_sem_descricoes_usa_codigo_padrao():
    codigos = {"31", "41", "46", "12", "21", "25"}
    r = resolver_conceitos(codigos, {})
    assert r.contas["receita_contraprestacoes"] == ["31"]
    assert r.origem["receita_contraprestacoes"] == "codigo_padrao"
