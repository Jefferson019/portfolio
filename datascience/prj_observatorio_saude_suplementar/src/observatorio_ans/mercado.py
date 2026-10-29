"""Indicadores de mercado: totais, razões ponderadas, distribuição e concentração.

As razões de mercado são calculadas sobre as SOMAS (ex.: sinistralidade do setor = soma das
despesas assistenciais / soma das contraprestações), como faz a ANS — e não pela média simples
das operadoras, que daria o mesmo peso a uma operadora de 2 mil e a uma de 5 milhões de vidas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .indicadores import calcular_razoes
from .plano_contas import CONCEITOS_FLUXO_TODOS, CONCEITOS_SALDO

RESULTADOS = [
    "tributos_diretos",
    "contraprestacoes_liquidas",
    "resultado_operacional",
    "resultado_financeiro",
    "resultado_patrimonial",
    "resultado_antes_impostos",
    "outros_resultados",
    "resultado_liquido",
    "aplicacoes_financeiras",
    "provisoes_tecnicas",
]
SOMAVEIS = (
    CONCEITOS_FLUXO_TODOS + CONCEITOS_SALDO + RESULTADOS + ["beneficiarios", "beneficiarios_medios"]
)
CHAVES = ["ano", "tri", "periodo", "janela", "recorte", "valor"]


def _expandir_recortes(ops: pd.DataFrame) -> pd.DataFrame:
    """Repete cada operadora em todos os recortes a que pertence."""
    partes = [
        ops.assign(recorte="setor", valor="todos"),
        ops.assign(recorte="segmento", valor=ops["segmento"]),
        ops.assign(recorte="modalidade", valor=ops["modalidade"]),
    ]
    if "porte" in ops:
        mh = ops[ops["segmento"].eq("medico_hospitalar")]
        partes.append(mh.assign(recorte="porte_mh", valor=mh["porte"]))
    return pd.concat(partes, ignore_index=True)


def _concentracao(grupo: pd.DataFrame) -> pd.Series:
    receita = grupo["receita_contraprestacoes"]
    receita = receita[receita > 0]
    total = receita.sum()
    if total <= 0 or len(receita) == 0:
        return pd.Series({"hhi": np.nan, "cr5": np.nan, "cr10": np.nan})
    fatias = (receita / total).sort_values(ascending=False)
    return pd.Series(
        {
            "hhi": float(((fatias * 100) ** 2).sum()),
            "cr5": float(fatias.head(5).sum()),
            "cr10": float(fatias.head(10).sum()),
        }
    )


def agregar_mercado(ops: pd.DataFrame, variante_sinistralidade: str) -> pd.DataFrame:
    base = _expandir_recortes(ops)
    somaveis = [c for c in SOMAVEIS if c in base]
    g = base.groupby(CHAVES, dropna=False)

    soma = g[somaveis].sum(min_count=1)
    # Operadoras com dados completos na janela (receita total não nula)
    contagens = g.agg(
        n_operadoras=("receita_total", lambda s: int(s.notna().sum())),
        pct_resultado_liquido_positivo=(
            "resultado_liquido",
            lambda s: float((s.dropna() > 0).mean()) if s.notna().any() else np.nan,
        ),
        n_resultado_liquido_positivo=("resultado_liquido", lambda s: int((s.dropna() > 0).sum())),
    )
    # Prejuízo operacional, entre quem tem receita de contraprestações
    com_receita = base[base["receita_contraprestacoes"] > 0]
    pct_ro = (
        com_receita.groupby(CHAVES, dropna=False)["resultado_operacional"]
        .agg(lambda s: float((s.dropna() < 0).mean()) if s.notna().any() else np.nan)
        .rename("pct_resultado_operacional_negativo")
    )

    # Distribuição da sinistralidade das operadoras (amostra válida, sem valores atípicos)
    validas = base[base["amostra_valida"] & ~base["sinistralidade_atipica"]]
    dist = (
        validas.groupby(CHAVES, dropna=False)["sinistralidade"]
        .quantile([0.25, 0.5, 0.75])
        .unstack()
    )
    dist.columns = ["sinistralidade_p25", "sinistralidade_mediana", "sinistralidade_p75"]

    concentracao = base.groupby(CHAVES, dropna=False)[["receita_contraprestacoes"]].apply(
        _concentracao
    )

    mercado = soma.join([contagens, pct_ro, dist, concentracao]).reset_index()
    mercado = calcular_razoes(mercado, variante_sinistralidade)
    return mercado.sort_values(CHAVES).reset_index(drop=True)


def top_operadoras(
    ops: pd.DataFrame, periodo: str, janela: str, segmento: str, n: int = 10
) -> pd.DataFrame:
    sub = ops[
        (ops["periodo"] == periodo) & (ops["janela"] == janela) & (ops["segmento"] == segmento)
    ]
    sub = sub[sub["receita_contraprestacoes"] > 0]
    total = sub["receita_contraprestacoes"].sum()
    top = sub.nlargest(n, "receita_contraprestacoes").copy()
    top["participacao"] = top["receita_contraprestacoes"] / total if total > 0 else np.nan
    return top
