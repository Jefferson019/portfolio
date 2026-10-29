"""Conciliação com os números oficiais divulgados pela ANS.

Cada linha de `referencias/ans_divulgacoes.csv` é um número publicado (com fonte e link). O
pipeline recalcula o mesmo número a partir dos dados brutos e marca se ficou dentro da tolerância.
Também serve para escolher, com evidência, a definição de sinistralidade que a ANS usa.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd

from .util import log


def carregar_referencias(caminho: Path | None = None) -> pd.DataFrame:
    if caminho is None:
        with (
            resources.files("observatorio_ans")
            .joinpath("referencias/ans_divulgacoes.csv")
            .open("r", encoding="utf-8") as f
        ):
            ref = pd.read_csv(f, dtype={"periodo": str})
    else:
        ref = pd.read_csv(caminho, dtype={"periodo": str})
    ref["valor_ans"] = pd.to_numeric(ref["valor_ans"], errors="coerce")
    ref["tolerancia"] = pd.to_numeric(ref["tolerancia"], errors="coerce")
    return ref


def _buscar(mercado: pd.DataFrame, linha: pd.Series, coluna: str) -> float:
    filtro = (
        (mercado["periodo"] == linha["periodo"])
        & (mercado["janela"] == linha["janela"])
        & (mercado["recorte"] == linha["recorte"])
        & (mercado["valor"] == linha["valor_recorte"])
    )
    achado = mercado.loc[filtro, coluna] if coluna in mercado else pd.Series(dtype=float)
    return float(achado.iloc[0]) if len(achado) and pd.notna(achado.iloc[0]) else np.nan


def _dentro(calculado: float, oficial: float, tolerancia: float, tipo: str) -> bool:
    if np.isnan(calculado) or np.isnan(oficial):
        return False
    if tipo == "rel":
        return abs(calculado - oficial) <= tolerancia * max(abs(oficial), 1e-9)
    return abs(calculado - oficial) <= tolerancia


def escolher_variante_sinistralidade(
    mercado: pd.DataFrame, referencias: pd.DataFrame
) -> tuple[str, dict]:
    """Escolhe 'bruta' ou 'liquida' pelo menor erro médio contra as sinistralidades oficiais."""
    linhas = referencias[referencias["indicador"] == "sinistralidade"]
    erros: dict[str, list[float]] = {"bruta": [], "liquida": []}
    for _, linha in linhas.iterrows():
        for variante in erros:
            v = _buscar(mercado, linha, f"sinistralidade_{variante}")
            if not np.isnan(v):
                erros[variante].append(abs(v - linha["valor_ans"]))
    resumo = {v: (float(np.mean(e)) if e else None) for v, e in erros.items()}
    n = {v: len(e) for v, e in erros.items()}
    if not erros["bruta"] or not erros["liquida"]:
        return "bruta", {
            "erro_medio": resumo,
            "comparacoes": n,
            "motivo": "sem referências no período; padrão = bruta",
        }
    escolhida = "bruta" if resumo["bruta"] <= resumo["liquida"] else "liquida"
    return escolhida, {
        "erro_medio": resumo,
        "comparacoes": n,
        "motivo": "menor erro médio contra a ANS",
    }


def conciliar(mercado: pd.DataFrame, referencias: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for _, ref in referencias.iterrows():
        calculado = _buscar(mercado, ref, ref["indicador"])
        if np.isnan(calculado):
            status = "sem_dados"
        elif _dentro(calculado, ref["valor_ans"], ref["tolerancia"], ref["tipo_tolerancia"]):
            status = "confere"
        else:
            status = "diverge"
        diferenca = calculado - ref["valor_ans"] if not np.isnan(calculado) else np.nan
        linhas.append(
            {
                **ref.to_dict(),
                "valor_calculado": calculado,
                "diferenca": diferenca,
                "diferenca_relativa": diferenca / abs(ref["valor_ans"])
                if ref["valor_ans"] and not np.isnan(diferenca)
                else np.nan,
                "status": status,
            }
        )
    resultado = pd.DataFrame(linhas)
    if not resultado.empty:
        contagem = resultado["status"].value_counts().to_dict()
        log.info("Conciliação com a ANS: %s", contagem)
    return resultado
