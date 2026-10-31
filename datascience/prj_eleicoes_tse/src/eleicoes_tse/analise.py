"""Indicadores calculados a partir das tabelas padronizadas (prata)."""

from __future__ import annotations

from importlib import resources

import numpy as np
import pandas as pd

from .util import pct

CARGOS_PERFIL = [
    "PRESIDENTE",
    "GOVERNADOR",
    "SENADOR",
    "DEPUTADO FEDERAL",
    "DEPUTADO ESTADUAL",
    "DEPUTADO DISTRITAL",
]
NEGROS = {"PRETA", "PARDA"}


# ------------------------------------------------------------------ resultado presidencial


def _rotulo_candidato(votos: pd.DataFrame) -> pd.DataFrame:
    """Nome de urna e partido de cada candidato (um por ano e número)."""
    return votos.groupby(["ano", "nr_candidato"], as_index=False).agg(
        candidato=("candidato", "first"), partido=("partido", "first")
    )


def resultado(votos: pd.DataFrame, nivel: list[str]) -> pd.DataFrame:
    """Votos e % dos votos válidos de cada candidato, agregados no nível pedido."""
    chave = ["ano", "turno", *nivel]
    t = votos.groupby([*chave, "nr_candidato"], as_index=False, dropna=False)["votos"].sum()
    t["pct_validos"] = pct(t["votos"], t.groupby(chave, dropna=False)["votos"].transform("sum"))
    t["posicao"] = t.groupby(chave, dropna=False)["votos"].rank(ascending=False, method="first")
    t = t.merge(_rotulo_candidato(votos), on=["ano", "nr_candidato"], how="left")
    colunas = [*chave, "posicao", "nr_candidato", "candidato", "partido", "votos", "pct_validos"]
    return t[colunas].sort_values([*chave, "posicao"]).reset_index(drop=True)


def vencedores(res: pd.DataFrame, nivel: list[str]) -> pd.DataFrame:
    """Primeiro colocado de cada recorte e a vantagem sobre o segundo (em pontos percentuais)."""
    chave = ["ano", "turno", *nivel]
    primeiro = res[res["posicao"] == 1].set_index(chave)
    segundo = res[res["posicao"] == 2].set_index(chave)["pct_validos"].rename("pct_segundo")
    out = primeiro.join(segundo)
    out["margem_pp"] = out["pct_validos"] - out["pct_segundo"].fillna(0)
    return out.reset_index()


def conferencia(nacional: pd.DataFrame) -> pd.DataFrame:
    """Compara o total nacional calculado com os resultados oficiais divulgados pelo TSE."""
    arquivo = resources.files("eleicoes_tse").joinpath("referencias/resultados_oficiais.csv")
    with arquivo.open(encoding="utf-8") as f:
        ref = pd.read_csv(f)
    ref = ref[ref["ano"].isin(nacional["ano"].unique())]
    calc = nacional[["ano", "turno", "nr_candidato", "votos"]].rename(
        columns={"votos": "votos_calculados"}
    )
    out = ref.merge(calc, on=["ano", "turno", "nr_candidato"], how="left")
    out["diferenca"] = out["votos_calculados"] - out["votos_oficiais"]
    out["diferenca_pct"] = pct(out["diferenca"], out["votos_oficiais"])
    out["confere"] = out["diferenca"].abs() <= 0.0001 * out["votos_oficiais"]
    return out


# ------------------------------------------------------------------ participação


def participacao(detalhe: pd.DataFrame, nivel: list[str]) -> pd.DataFrame:
    chave = ["ano", "turno", *nivel]
    cols = ["aptos", "comparecimento", "abstencoes", "validos", "brancos", "nulos"]
    t = detalhe.groupby(chave, as_index=False, dropna=False)[cols].sum()
    t["pct_abstencao"] = pct(t["abstencoes"], t["aptos"])
    t["pct_brancos"] = pct(t["brancos"], t["comparecimento"])
    t["pct_nulos"] = pct(t["nulos"], t["comparecimento"])
    t["pct_validos"] = pct(t["validos"], t["comparecimento"])
    return t


# ------------------------------------------------------------------ dinâmica entre turnos e anos


def finalistas(nacional: pd.DataFrame, ano: int) -> pd.DataFrame:
    """Os dois candidatos do 2º turno (ou os dois primeiros do 1º, se não houve 2º)."""
    n = nacional[nacional["ano"] == ano]
    turno = n["turno"].max()
    return n[(n["turno"] == turno) & (n["posicao"] <= 2)].sort_values("posicao")


def entre_turnos(municipal: pd.DataFrame, nacional: pd.DataFrame) -> pd.DataFrame:
    """Por município: % de cada finalista no 1º e no 2º turno e o ganho entre os turnos."""
    linhas = []
    for ano in sorted(nacional["ano"].unique()):
        if nacional.loc[nacional["ano"] == ano, "turno"].nunique() < 2:
            continue
        for _, fin in finalistas(nacional, ano).iterrows():
            m = municipal[
                (municipal["ano"] == ano) & (municipal["nr_candidato"] == fin["nr_candidato"])
            ]
            larga = m.pivot_table(
                index=["uf", "cd_municipio", "municipio"], columns="turno", values="pct_validos"
            ).reset_index()
            larga.columns = ["uf", "cd_municipio", "municipio", "pct_1t", "pct_2t"]
            larga.insert(0, "ano", ano)
            larga.insert(1, "candidato", fin["candidato"])
            larga.insert(2, "partido", fin["partido"])
            larga["ganho_pp"] = larga["pct_2t"] - larga["pct_1t"]
            linhas.append(larga)
    return pd.concat(linhas, ignore_index=True) if linhas else pd.DataFrame()


def comparacao_anos(municipal: pd.DataFrame, ano_a: int, ano_b: int) -> pd.DataFrame:
    """% de cada partido presente no último turno dos dois anos, por município, e a variação."""

    def ultimo_turno(ano):
        m = municipal[municipal["ano"] == ano]
        return m[m["turno"] == m["turno"].max()]

    a, b = ultimo_turno(ano_a), ultimo_turno(ano_b)
    partidos = sorted(set(a["partido"]) & set(b["partido"]))
    chave = ["uf", "cd_municipio", "municipio"]
    linhas = []
    for partido in partidos:
        pa = a[a["partido"] == partido][[*chave, "candidato", "pct_validos"]]
        pb = b[b["partido"] == partido][[*chave, "candidato", "pct_validos"]]
        j = pa.merge(pb, on=chave, suffixes=(f"_{ano_a}", f"_{ano_b}"))
        j.insert(0, "partido", partido)
        j["variacao_pp"] = j[f"pct_validos_{ano_b}"] - j[f"pct_validos_{ano_a}"]
        linhas.append(j)
    return pd.concat(linhas, ignore_index=True) if linhas else pd.DataFrame()


def correlacao_ponderada(x: pd.Series, y: pd.Series, peso: pd.Series) -> float:
    mx, my = np.average(x, weights=peso), np.average(y, weights=peso)
    cov = np.average((x - mx) * (y - my), weights=peso)
    return float(
        cov
        / np.sqrt(np.average((x - mx) ** 2, weights=peso) * np.average((y - my) ** 2, weights=peso))
    )


# ------------------------------------------------------------------ perfil das candidaturas


def perfil_candidaturas(cand: pd.DataFrame) -> pd.DataFrame:
    """% de mulheres e de pessoas negras (pretas + pardas) entre candidaturas aptas e entre eleitos."""
    c = cand[cand["apta"] & cand["cargo"].isin(CARGOS_PERFIL)].copy()
    c.loc[c["cargo"] == "DEPUTADO DISTRITAL", "cargo"] = "DEPUTADO ESTADUAL"
    c["mulher"] = c["genero"].str.upper().eq("FEMININO")
    c["negra"] = c["cor_raca"].str.upper().isin(NEGROS)
    c["cor_informada"] = c["cor_raca"].notna() & ~c["cor_raca"].str.upper().isin(
        {"NÃO INFORMADO", "NAO INFORMADO", "NÃO DIVULGÁVEL", "SEM INFORMAÇÃO"}
    )

    def resumir(g: pd.DataFrame) -> pd.Series:
        e = g[g["eleito"]]
        return pd.Series(
            {
                "candidaturas": len(g),
                "eleitos": len(e),
                "pct_mulheres_candidaturas": pct(g["mulher"].sum(), len(g)) if len(g) else np.nan,
                "pct_mulheres_eleitos": pct(e["mulher"].sum(), len(e)) if len(e) else np.nan,
                "pct_negros_candidaturas": pct(g["negra"].sum(), g["cor_informada"].sum())
                if g["cor_informada"].any()
                else np.nan,
                "pct_negros_eleitos": pct(e["negra"].sum(), e["cor_informada"].sum())
                if e["cor_informada"].any()
                else np.nan,
                "idade_mediana_candidaturas": g["idade"].median(),
                "idade_mediana_eleitos": e["idade"].median(),
            }
        )

    por_cargo = c.groupby(["ano", "cargo"]).apply(resumir, include_groups=False).reset_index()
    total = c.groupby(["ano"]).apply(resumir, include_groups=False).reset_index()
    total.insert(1, "cargo", "TODOS")
    out = pd.concat([por_cargo, total], ignore_index=True)
    ordem = {cargo: i for i, cargo in enumerate([*CARGOS_PERFIL, "TODOS"])}
    return out.sort_values(
        ["ano", "cargo"], key=lambda s: s.map(ordem) if s.name == "cargo" else s
    ).reset_index(drop=True)


def instrucao_eleitos(cand: pd.DataFrame) -> pd.DataFrame:
    c = cand[cand["apta"] & cand["cargo"].isin(CARGOS_PERFIL)]
    t = c.groupby(["ano", "instrucao"]).agg(
        candidaturas=("sq_candidato", "size"), eleitos=("eleito", "sum")
    )
    t["pct_candidaturas"] = pct(
        t["candidaturas"], t.groupby("ano")["candidaturas"].transform("sum")
    )
    t["pct_eleitos"] = pct(t["eleitos"], t.groupby("ano")["eleitos"].transform("sum"))
    t["taxa_sucesso"] = pct(t["eleitos"], t["candidaturas"])
    return t.reset_index()
