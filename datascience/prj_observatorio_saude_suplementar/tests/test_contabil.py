import numpy as np
import pandas as pd
import pytest

from observatorio_ans.contabil import calcular_janelas, detectar_modo_acumulacao, normalizar_sinais
from observatorio_ans.mercado import _concentracao
from observatorio_ans.util import normalizar_texto


def _df(linhas):
    return pd.DataFrame(
        linhas, columns=["reg_ans", "conta", "descricao", "saldo_inicial", "saldo_final"]
    )


DESC = {
    "31": "CONTRAPRESTACOES",
    "32": "(-) TRIBUTOS DIRETOS DE OPERACOES",
    "41": "EVENTOS",
    "21": "PASSIVO CIRCULANTE",
    "12": "ATIVO CIRCULANTE",
}


@pytest.mark.parametrize("convencao", ["absoluta", "credora_negativa"])
def test_normalizar_sinais_converge_para_mesma_convencao(convencao):
    linhas = []
    for i in range(5):
        r = f"{i:06d}"
        rc, trib, ev, pc, ac = 1000.0 + i, 10.0, 800.0, 300.0, 500.0
        if convencao == "absoluta":
            valores = {"31": rc, "32": trib, "41": ev, "21": pc, "12": ac}
        else:
            valores = {"31": -rc, "32": trib, "41": ev, "21": -pc, "12": ac}
        for conta, v in valores.items():
            linhas.append((r, conta, DESC[conta], 0.0, v))
    df, info = normalizar_sinais(_df(linhas), {k: normalizar_texto(v) for k, v in DESC.items()})
    por = df.pivot(index="reg_ans", columns="conta", values="saldo_final")
    assert (por["31"] > 0).all() and (por["41"] > 0).all() and (por["21"] > 0).all()
    assert (por["32"] < 0).all(), "tributos diretos devem ficar negativos (dedução)"


def _conceitos(modo):
    """Uma operadora, dois anos, receita de 100 mil por trimestre (crescendo 10 mil por ano)."""
    linhas = []
    for ano in (2024, 2025):
        acumulado = 0.0
        for tri in (1, 2, 3, 4):
            fluxo = 100_000.0 + (ano - 2024) * 10_000
            anterior = acumulado
            acumulado += fluxo
            if modo == "acumulado":
                si, sf = anterior, acumulado
            else:
                si, sf = 0.0, fluxo
            linhas.append(("000001", ano, tri, "receita_contraprestacoes", si, sf))
            linhas.append(("000001", ano, tri, "despesa_assistencial", si * 0.8, sf * 0.8))
            linhas.append(("000001", ano, tri, "ativo_circulante", np.nan, 500_000.0))
    return pd.DataFrame(
        linhas, columns=["reg_ans", "ano", "tri", "conceito", "saldo_inicial", "saldo_final"]
    )


@pytest.mark.parametrize("modo", ["acumulado", "trimestral"])
def test_janelas_nos_dois_modos_de_acumulacao(modo):
    conceitos = _conceitos(modo)
    # Repete a operadora para ter pares suficientes na detecção
    conceitos = pd.concat(
        [conceitos.assign(reg_ans=f"{i:06d}") for i in range(12)], ignore_index=True
    )
    modos = detectar_modo_acumulacao(conceitos)
    assert modos[2025]["modo"] == modo
    j = (
        calcular_janelas(conceitos, modos)
        .query("reg_ans == '000001'")
        .set_index(["janela", "periodo"])
    )
    assert j.loc[("acumulado_ano", "2025T2"), "receita_contraprestacoes"] == pytest.approx(220_000)
    assert j.loc[("trimestre", "2025T3"), "receita_contraprestacoes"] == pytest.approx(110_000)
    # 12 meses até 2025T2 = 2 trimestres de 2024 (100 mil) + 2 de 2025 (110 mil)
    assert j.loc[("12_meses", "2025T2"), "receita_contraprestacoes"] == pytest.approx(420_000)
    assert np.isnan(j.loc[("12_meses", "2024T2"), "receita_contraprestacoes"])
    assert j.loc[("12_meses", "2025T2"), "ativo_circulante"] == pytest.approx(500_000)


def test_concentracao_hhi():
    grupo = pd.DataFrame({"receita_contraprestacoes": [50.0, 30.0, 20.0, 0.0]})
    c = _concentracao(grupo)
    assert c["hhi"] == pytest.approx(50**2 + 30**2 + 20**2)
    assert c["cr5"] == pytest.approx(1.0)


def test_codigos_em_largura_fixa_viram_hierarquicos(tmp_path):
    import zipfile

    from observatorio_ans.contabil import ler_trimestre

    linhas = [
        '"DATA";"REG_ANS";"CD_CONTA_CONTABIL";"DESCRICAO";"VL_SALDO_INICIAL";"VL_SALDO_FINAL"'
    ]
    for conta, desc in [
        ("100000000", "ATIVO"),
        ("120000000", "ATIVO CIRCULANTE"),
        ("310000000", "CONTRAPRESTACOES"),
        ("410000000", "EVENTOS"),
        ("411000000", "EVENTOS AVISADOS"),
        ("411111013", "ANALITICA"),
    ]:
        linhas.append(f'"2026-01-01";"5711";"{conta}";"{desc}";"0,00";"100,50"')
    caminho = tmp_path / "1T2026.zip"
    with zipfile.ZipFile(caminho, "w") as zf:
        zf.writestr("1T2026.csv", "\n".join(linhas).encode("utf-8"))
    df, info = ler_trimestre(caminho)
    assert info["codigos_largura_fixa"] is True
    assert set(df["conta"]) == {
        "1",
        "12",
        "31",
        "41",
        "411",
    }  # a analítica (9 dígitos) fica de fora
    assert (df["reg_ans"] == "005711").all() and (df["saldo_final"] == 100.5).all()


def test_listagem_de_indice_no_estilo_do_portal(monkeypatch):
    from observatorio_ans.fontes import ClienteANS

    html = """<html><body><h1>Index of /FTP/PDA/demonstracoes_contabeis/2025</h1><table>
    <tr><th><a href="?C=N;O=D">Name</a></th><th><a href="?C=M;O=A">Last modified</a></th></tr>
    <tr><td><a href="/FTP/PDA/demonstracoes_contabeis/">Parent Directory</a></td></tr>
    <tr><td><a href="1T2025.zip">1T2025.zip</a></td><td>2025-06-03 10:00</td><td>7.9M</td></tr>
    <tr><td><a href="2T2025.zip">2T2025.zip</a></td><td>2025-09-02 17:07</td><td>8.8M</td></tr>
    <tr><td><a href="informacoes_consolidadas_de_beneficiarios-024/">informacoes_consolid..&gt;</a></td></tr>
    </table></body></html>"""

    class Resposta:
        text = html

    cliente = ClienteANS("https://dadosabertos.ans.gov.br/FTP/PDA/")
    monkeypatch.setattr(cliente, "_requisitar", lambda *a, **k: Resposta())
    entradas = cliente.listar("demonstracoes_contabeis/2025/")
    assert [(e.nome, e.diretorio) for e in entradas] == [
        ("1T2025.zip", False),
        ("2T2025.zip", False),
        ("informacoes_consolidadas_de_beneficiarios-024", True),
    ]
    assert (
        entradas[0].url
        == "https://dadosabertos.ans.gov.br/FTP/PDA/demonstracoes_contabeis/2025/1T2025.zip"
    )


def test_razoes_usam_a_base_da_variante_escolhida():
    from observatorio_ans.indicadores import calcular_razoes

    d = pd.DataFrame(
        {
            "janela": ["12_meses"],
            "receita_contraprestacoes": [1000.0],
            "contraprestacoes_liquidas": [980.0],
            "despesa_assistencial": [800.0],
            "despesa_administrativa": [100.0],
            "despesa_comercializacao": [20.0],
            "resultado_operacional": [50.0],
            "resultado_liquido": [40.0],
            "receita_total": [1100.0],
            "ativo_circulante": [500.0],
            "passivo_circulante": [250.0],
            "realizavel_longo_prazo": [0.0],
            "passivo_nao_circulante": [0.0],
            "patrimonio_liquido": [400.0],
            "aplicacoes_financeiras": [300.0],
            "provisoes_tecnicas": [200.0],
            "creditos_operacoes_planos": [49.0],
        }
    )
    bruta = calcular_razoes(d, "bruta").iloc[0]
    liquida = calcular_razoes(d, "liquida").iloc[0]
    assert bruta["sinistralidade"] == pytest.approx(0.8) and bruta[
        "indice_combinado"
    ] == pytest.approx(0.92)
    assert liquida["sinistralidade"] == pytest.approx(800 / 980)
    assert liquida["indice_combinado"] == pytest.approx(920 / 980)  # mesma base em todas as razões
    assert liquida["receita_base"] == pytest.approx(980)
