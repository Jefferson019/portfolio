"""Indicadores por operadora: resultados, sinistralidade, despesas, margens, liquidez e rentabilidade.

Todas as fórmulas estão documentadas em docs/indicadores.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MODALIDADE_NAO_IDENTIFICADA
from .util import dividir

# Receita mínima (na janela) para entrar em distribuições e rankings: evita razões sem sentido
# de operadoras em liquidação ou sem operação relevante.
RECEITA_MINIMA_RANKING = 1_000_000.0
FAIXA_SINISTRALIDADE_PLAUSIVEL = (0.2, 2.0)

INDICADORES = {
    "sinistralidade": "Sinistralidade",
    "sinistralidade_bruta": "Sinistralidade (sobre contraprestações brutas)",
    "sinistralidade_liquida": "Sinistralidade (sobre contraprestações líquidas de tributos)",
    "indice_despesa_administrativa": "Despesa administrativa / contraprestações",
    "indice_despesa_comercializacao": "Despesa de comercialização / contraprestações",
    "indice_combinado": "Índice combinado",
    "margem_operacional": "Margem operacional",
    "margem_liquida": "Margem líquida",
    "liquidez_corrente": "Liquidez corrente",
    "liquidez_geral": "Liquidez geral",
    "endividamento": "Endividamento (passivo exigível / PL)",
    "roe": "Retorno sobre o PL (12 meses)",
    "pmcr_dias": "Prazo médio de recebimento de contraprestações (dias)",
    "cobertura_provisoes": "Aplicações financeiras / provisões técnicas",
    "receita_por_beneficiario_mes": "Receita de contraprestações por beneficiário (R$/mês)",
    "despesa_assistencial_por_beneficiario_mes": "Despesa assistencial por beneficiário (R$/mês)",
}


def calcular_resultados(df: pd.DataFrame) -> pd.DataFrame:
    """Resultados da DRE a partir dos conceitos (valores já com sinais normalizados)."""
    d = df.copy()
    d["tributos_diretos"] = d["tributos_diretos_operacoes"] + d["tributos_diretos_outras"]
    d["contraprestacoes_liquidas"] = d["receita_contraprestacoes"] + d["tributos_diretos_operacoes"]
    d["resultado_operacional"] = (
        d["receita_contraprestacoes"]
        + d["tributos_diretos"]
        + d["outras_receitas_operacionais"]
        - d["despesa_assistencial"]
        - d["despesa_comercializacao"]
        - d["despesa_administrativa"]
        - d["outras_despesas_operacionais"]
    )
    d["resultado_financeiro"] = d["receitas_financeiras"] - d["despesas_financeiras"]
    d["resultado_patrimonial"] = d["receitas_patrimoniais"] - d["despesas_patrimoniais"]
    d["resultado_antes_impostos"] = d["receita_total"] - d["despesa_total"]
    d["outros_resultados"] = d["resultado_antes_impostos"] - (
        d["resultado_operacional"] + d["resultado_financeiro"] + d["resultado_patrimonial"]
    )
    d["resultado_liquido"] = d["resultado_antes_impostos"] - d["impostos_participacoes"]
    d["aplicacoes_financeiras"] = d["aplicacoes_financeiras_cp"].fillna(0) + d[
        "aplicacoes_financeiras_lp"
    ].fillna(0)
    d.loc[
        d["aplicacoes_financeiras_cp"].isna() & d["aplicacoes_financeiras_lp"].isna(),
        "aplicacoes_financeiras",
    ] = np.nan
    d["provisoes_tecnicas"] = d["provisoes_tecnicas_cp"].fillna(0) + d[
        "provisoes_tecnicas_lp"
    ].fillna(0)
    d.loc[
        d["provisoes_tecnicas_cp"].isna() & d["provisoes_tecnicas_lp"].isna(), "provisoes_tecnicas"
    ] = np.nan
    return d


def calcular_razoes(d: pd.DataFrame, variante_sinistralidade: str = "bruta") -> pd.DataFrame:
    """Razões. Funciona tanto para operadoras quanto para somas de mercado (mesmas colunas)."""
    d = d.copy()
    rc = d["receita_contraprestacoes"]
    d["sinistralidade_bruta"] = dividir(d["despesa_assistencial"], rc)
    d["sinistralidade_liquida"] = dividir(d["despesa_assistencial"], d["contraprestacoes_liquidas"])
    d["sinistralidade"] = d[f"sinistralidade_{variante_sinistralidade}"]
    # Todas as razões sobre a receita usam a mesma base da sinistralidade adotada, para que
    # "de cada R$ 100 de mensalidade" some corretamente (assistencial + administrativa + ...)
    base = d["contraprestacoes_liquidas"] if variante_sinistralidade == "liquida" else rc
    d["receita_base"] = base
    d["indice_despesa_administrativa"] = dividir(d["despesa_administrativa"], base)
    d["indice_despesa_comercializacao"] = dividir(d["despesa_comercializacao"], base)
    d["indice_combinado"] = dividir(
        d["despesa_assistencial"] + d["despesa_administrativa"] + d["despesa_comercializacao"], base
    )
    d["margem_operacional"] = dividir(d["resultado_operacional"], base)
    d["margem_liquida"] = dividir(d["resultado_liquido"], d["receita_total"])
    d["liquidez_corrente"] = dividir(d["ativo_circulante"], d["passivo_circulante"])
    d["liquidez_geral"] = dividir(
        d["ativo_circulante"] + d["realizavel_longo_prazo"].fillna(0),
        d["passivo_circulante"] + d["passivo_nao_circulante"].fillna(0),
    )
    d["endividamento"] = dividir(
        d["passivo_circulante"] + d["passivo_nao_circulante"].fillna(0), d["patrimonio_liquido"]
    )
    d["cobertura_provisoes"] = dividir(d["aplicacoes_financeiras"], d["provisoes_tecnicas"])

    doze = d["janela"].eq("12_meses")
    d["roe"] = np.where(doze, dividir(d["resultado_liquido"], d["patrimonio_liquido"]), np.nan)
    d["pmcr_dias"] = np.where(doze, dividir(d["creditos_operacoes_planos"], base) * 360, np.nan)

    if "beneficiarios_medios" in d:
        benef = d["beneficiarios_medios"]
        d["receita_por_beneficiario_mes"] = np.where(doze, dividir(rc, benef) / 12, np.nan)
        d["despesa_assistencial_por_beneficiario_mes"] = np.where(
            doze, dividir(d["despesa_assistencial"], benef) / 12, np.nan
        )
    return d


def montar_operadoras(janelas: pd.DataFrame, cadastro: pd.DataFrame) -> pd.DataFrame:
    """Junta conceitos por janela com o cadastro e calcula os resultados."""
    d = calcular_resultados(janelas)
    colunas_cadastro = [
        "reg_ans",
        "nome",
        "razao_social",
        "cnpj",
        "modalidade",
        "segmento",
        "uf",
        "cidade",
        "situacao",
    ]
    d = d.merge(cadastro[colunas_cadastro], on="reg_ans", how="left")
    d["modalidade"] = d["modalidade"].fillna(MODALIDADE_NAO_IDENTIFICADA)
    d["segmento"] = d["segmento"].fillna("nao_identificado")
    d["nome"] = d["nome"].fillna("Registro ANS " + d["reg_ans"])
    d["situacao"] = d["situacao"].fillna("desconhecida")
    return d


def finalizar_operadoras(d: pd.DataFrame, variante_sinistralidade: str) -> pd.DataFrame:
    d = d.copy()
    if "benef_medico_medio" in d:
        odonto = d["segmento"].eq("odontologico")
        d["beneficiarios_medios"] = np.where(
            odonto, d["benef_odonto_medio"], d["benef_medico_medio"]
        )
    d = calcular_razoes(d, variante_sinistralidade)
    d["amostra_valida"] = d["receita_contraprestacoes"].ge(RECEITA_MINIMA_RANKING) & d[
        "segmento"
    ].isin(["medico_hospitalar", "odontologico"])
    baixo, alto = FAIXA_SINISTRALIDADE_PLAUSIVEL
    d["sinistralidade_atipica"] = d["sinistralidade"].notna() & ~d["sinistralidade"].between(
        baixo, alto
    )
    return d
