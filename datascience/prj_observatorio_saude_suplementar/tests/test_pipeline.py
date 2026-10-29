"""Teste ponta a ponta: o pipeline roda contra o espelho sintético e reproduz o gabarito."""

import json

import numpy as np
import pandas as pd
import pytest


def _gabarito_ytd(gab: pd.DataFrame) -> pd.DataFrame:
    g = gab.copy()
    rn = g["rn290"]
    return pd.DataFrame(
        {
            "reg_ans": g["reg_ans"],
            "ano": g["ano"],
            "tri": g["tri"],
            "receita_contraprestacoes": g["c_31"],
            "despesa_assistencial": g["c_41"],
            "despesa_administrativa": g["c_46"],
            "despesa_comercializacao": g["c_43"],
            "receitas_financeiras": np.where(rn, g["c_34"], g["c_35"]),
            "tributos_diretos_operacoes": np.where(rn, 0.0, g["c_32"]),
            "receita_total": g["c_3"],
            "resultado_liquido": g["c_3"] - g["c_4"] - g["c_61"],
            "patrimonio_liquido": g["b_25"],
            "aplicacoes_financeiras": g["b_122"] + g["b_1311"] + g["b_1312"],
            "provisoes_tecnicas": g["b_211"] + g["b_231"],
        }
    )


COLUNAS = [
    "receita_contraprestacoes",
    "despesa_assistencial",
    "despesa_administrativa",
    "despesa_comercializacao",
    "receitas_financeiras",
    "tributos_diretos_operacoes",
    "receita_total",
    "resultado_liquido",
    "patrimonio_liquido",
    "aplicacoes_financeiras",
    "provisoes_tecnicas",
]


def test_valores_acumulados_conferem_com_gabarito(espelho, execucao):
    gab = _gabarito_ytd(espelho["gabarito"])
    ops = execucao["ops"].query("janela == 'acumulado_ano'")
    junto = ops.merge(gab, on=["reg_ans", "ano", "tri"], suffixes=("", "_gab"))
    assert len(junto) == len(gab), "toda operadora/trimestre do gabarito deve aparecer"
    for coluna in COLUNAS:
        erro = (junto[coluna] - junto[f"{coluna}_gab"]).abs().max()
        assert erro < 0.10, f"{coluna}: erro máximo {erro}"  # só arredondamento de centavos


def test_sinistralidade_e_janelas(espelho, execucao):
    ops = execucao["ops"]
    gab = espelho["gabarito"]
    linha = gab[(gab["ano"] == 2026) & (gab["tri"] == 2)].iloc[0]
    calc = ops[
        (ops["reg_ans"] == linha["reg_ans"])
        & (ops["periodo"] == "2026T2")
        & (ops["janela"] == "acumulado_ano")
    ]
    assert calc["sinistralidade"].iloc[0] == pytest.approx(linha["c_41"] / linha["c_31"], rel=1e-6)
    # janela de 12 meses na virada do ano = acumulado do 4º trimestre
    doze = ops[(ops["periodo"] == "2025T4") & (ops["janela"] == "12_meses")].set_index("reg_ans")
    ano = ops[(ops["periodo"] == "2025T4") & (ops["janela"] == "acumulado_ano")].set_index(
        "reg_ans"
    )
    pd.testing.assert_series_equal(
        doze["receita_contraprestacoes"], ano["receita_contraprestacoes"]
    )


def test_trimestre_faltante_gera_lacuna(execucao):
    ops = execucao["ops"]
    da_operadora = ops[ops["reg_ans"] == "300063"]  # 10ª operadora (índice 9) não entregou 2025T3
    assert da_operadora.query("periodo == '2025T3'").empty
    t4 = da_operadora.query("periodo == '2025T4' and janela == 'trimestre'")
    assert t4["receita_contraprestacoes"].isna().all()


def test_cadastro_e_segmentos(execucao):
    ops = execucao["ops"]
    fora = ops.query("reg_ans == '300021'")  # 4ª operadora não está no cadastro
    assert (fora["modalidade"] == "Não identificada").all()
    assert set(ops["segmento"]) >= {
        "medico_hospitalar",
        "odontologico",
        "administradora",
        "nao_identificado",
    }
    cancelada = ops.query("reg_ans == '300035'")
    assert (cancelada["situacao"] == "cancelada").all()


def test_beneficiarios_e_porte(espelho, execucao):
    hist = pd.read_csv(
        execucao["historico"] / "beneficiarios_operadora.csv.gz",
        dtype={"competencia": str, "reg_ans": str},
    )
    # mês mais recente + 5 fins de trimestre + mesmo mês do ano anterior; 202412 e 202607 não entram
    assert sorted(hist["competencia"].unique()) == [
        "202506",
        "202508",
        "202509",
        "202512",
        "202603",
        "202606",
        "202608",
    ]
    meta = espelho["gabarito"].drop_duplicates("reg_ans").set_index("reg_ans")
    total = hist[hist["competencia"] == "202608"].groupby("reg_ans")["beneficiarios"].sum()
    esperado = meta.loc[total.index, "beneficiarios"] * (1 + 0.004 * 8)
    assert ((total - esperado).abs() / esperado).max() < 0.01
    ops = execucao["ops"]
    assert set(ops.loc[ops["segmento"] == "medico_hospitalar", "porte"]) <= {
        "pequeno",
        "medio",
        "grande",
        "sem_informacao",
        "sem_beneficiarios",
    }
    assert (ops.loc[ops["segmento"] == "administradora", "porte"] == "nao_se_aplica").all()


def test_mercado_usa_somas_ponderadas(execucao):
    ops, merc = execucao["ops"], execucao["mercado"]
    filtro = (
        (ops["periodo"] == "2026T2")
        & (ops["janela"] == "acumulado_ano")
        & (ops["segmento"] == "medico_hospitalar")
    )
    esperado = (
        ops.loc[filtro, "despesa_assistencial"].sum()
        / ops.loc[filtro, "receita_contraprestacoes"].sum()
    )
    linha = merc.query(
        "periodo == '2026T2' and janela == 'acumulado_ano' and recorte == 'segmento' and valor == 'medico_hospitalar'"
    )
    assert linha["sinistralidade_bruta"].iloc[0] == pytest.approx(esperado)
    assert linha["n_operadoras"].iloc[0] == filtro.sum()
    assert 0 < linha["hhi"].iloc[0] <= 10_000


def test_relatorio_de_qualidade(execucao):
    q = json.loads(execucao["qualidade_path"].read_text(encoding="utf-8"))
    assert q["periodo_mais_recente"] == "2026T2"
    assert q["acumulacao"]["2025"]["modo"] == "acumulado"
    assert q["conceitos"]["2025T1"]["sinais"]["classes_invertidas"] == ["2", "3"]
    assert q["conceitos"]["2024T1"]["sinais"]["redutoras_invertidas"] == ["32", "34"]
    assert q["conceitos"]["2023T1"]["resolucao"]["contas"]["receitas_financeiras"] == ["34"]
    assert q["leitura"]["2023T1"]["encoding"] == "latin-1"
    assert q["sinistralidade"]["variante"] in {"bruta", "liquida"}


def test_conciliacao_tem_todas_as_referencias(execucao):
    conc = execucao["conciliacao"]
    assert {"valor_ans", "valor_calculado", "status", "url"} <= set(conc.columns)
    assert set(conc["status"]) <= {"confere", "diverge", "sem_dados"}
    # períodos fora do espelho (2023T2, por exemplo, existe; 2018 não) não quebram nada
    assert len(conc) > 50


def test_painel_gerado_com_dados_embutidos(execucao):
    import re

    html = (execucao["site"] / "index.html").read_text(encoding="utf-8")
    assert "/*__DADOS__*/" not in html and "__TITULO__" not in html
    bloco = re.search(r'<script id="dados" type="application/json">(.*?)</script>', html, re.S)
    dados = json.loads(bloco.group(1))
    assert dados["meta"]["periodo_mais_recente"] == "2026T2"
    assert dados["mercado"]["rows"] and dados["operadoras"]["rows"] and dados["series"]["rows"]
    assert dados["beneficiarios"]["competencia"] == "202608"
    for arquivo in (
        "mercado_indicadores.csv",
        "operadoras_ultimo_trimestre.csv",
        "conciliacao_ans.csv",
    ):
        assert (execucao["site"] / "dados" / arquivo).exists()


def test_tabela_do_painel_preserva_tipos():
    import numpy as np

    from observatorio_ans.painel import _tabela

    df = pd.DataFrame(
        {
            "op": np.array([1, 2]),
            "amostra": np.array([True, False]),
            "nome": ["A", None],
            "sinistralidade": [0.81234567, np.nan],
        }
    )
    t = _tabela(df, list(df.columns), {"sinistralidade": 4})
    assert t["rows"] == [[1, True, "A", 0.8123], [2, False, None, None]]
    json.dumps(t, allow_nan=False)  # nada de NaN no JSON
