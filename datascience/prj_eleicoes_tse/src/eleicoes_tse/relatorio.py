"""Gera relatorio/RELATORIO.md com os números e gráficos da última execução."""

from __future__ import annotations

import pandas as pd

from .config import Config


def _n(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def _p(v, casas: int = 1) -> str:
    return "–" if pd.isna(v) else f"{v:.{casas}f}%".replace(".", ",")


def _pp(v) -> str:
    return f"{v:+.1f} p.p.".replace(".", ",")


def _tabela(linhas: list[list[str]], cabecalho: list[str]) -> str:
    out = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join(["---"] * len(cabecalho)) + "|"]
    out += ["| " + " | ".join(map(str, linha)) + " |" for linha in linhas]
    return "\n".join(out)


def escrever_relatorio(cfg: Config, r: dict) -> None:
    anos, nacional, figs = r["anos"], r["nacional"], r["figs"]
    s: list[str] = []
    s.append("# Eleições gerais no Brasil — análise com os dados abertos do TSE\n")
    s.append(
        f"Relatório gerado automaticamente em **{r['resumo']['gerado_em']}** por `python -m eleicoes_tse` "
        f"a partir dos arquivos baixados do repositório de dados abertos do TSE "
        f"([cdn.tse.jus.br/estatistica/sead/odsele](https://dadosabertos.tse.jus.br/)). "
        f"Anos analisados: **{', '.join(map(str, anos))}**. As tabelas usadas em cada número estão em "
        f"[`dados/resultados/`](../dados/resultados/).\n"
    )

    # ---------------------------------------------------------- 1. resultado nacional
    s.append("## 1. Resultado nacional para presidente\n")
    for ano in anos:
        for turno in sorted(nacional.loc[nacional["ano"] == ano, "turno"].unique()):
            d = nacional[(nacional["ano"] == ano) & (nacional["turno"] == turno)].head(6)
            s.append(f"**{ano} — {turno}º turno**\n")
            s.append(_tabela([[int(x.posicao), x.candidato, x.partido, _n(x.votos), _p(x.pct_validos, 2)] for x in d.itertuples()],
                             ["#", "Candidato", "Partido", "Votos", "% válidos"]) + "\n")  # fmt: skip

    conf = r["conf"]
    if len(conf):
        ok = int(conf["confere"].sum())
        s.append("### Conferência com o resultado oficial\n")
        s.append(
            f"Os totais acima foram somados a partir dos arquivos por município e zona e comparados com os "
            f"números oficiais divulgados pelo TSE: **{ok} de {len(conf)} conferem** (tolerância de 0,01%). "
            "Detalhe em [`conferencia_tse.csv`](../dados/resultados/conferencia_tse.csv).\n"
        )
        s.append(_tabela([[x.ano, f"{x.turno}º", x.candidato, _n(x.votos_oficiais),
                           "–" if pd.isna(x.votos_calculados) else _n(x.votos_calculados), "✅" if x.confere else "❌"]
                          for x in conf.itertuples()], ["Ano", "Turno", "Candidato", "Oficial", "Calculado", ""]) + "\n")  # fmt: skip

    # ---------------------------------------------------------- 2. geografia
    s.append("## 2. Geografia do voto\n")
    regiao = r["regiao"]
    for ano in anos:
        turno = nacional.loc[nacional["ano"] == ano, "turno"].max()
        fin = nacional[
            (nacional["ano"] == ano) & (nacional["turno"] == turno) & (nacional["posicao"] <= 2)
        ]
        d = regiao[
            (regiao["ano"] == ano)
            & (regiao["turno"] == turno)
            & regiao["nr_candidato"].isin(fin["nr_candidato"])
        ]
        larga = d.pivot_table(index="regiao", columns="candidato", values="pct_validos")
        larga = larga[fin["candidato"].tolist()]
        s.append(f"**{ano}, {turno}º turno — % dos válidos por região**\n")
        s.append(
            _tabela(
                [[reg, *[_p(v) for v in linha]] for reg, linha in larga.iterrows()],
                ["Região", *larga.columns],
            )
            + "\n"
        )
        s.append(f"![Resultado por UF {ano}](figuras/{figs[f'uf_{ano}']})\n")

    venc_uf = r["venc_uf"]
    vu = venc_uf[venc_uf["uf"] != "ZZ"]
    linhas = []
    for ano in anos:
        turno = vu.loc[vu["ano"] == ano, "turno"].max()
        d = vu[(vu["ano"] == ano) & (vu["turno"] == turno)]
        cont = d.groupby("candidato").size().sort_values(ascending=False)
        apertada = d.sort_values("margem_pp").iloc[0]
        linhas.append([ano, "; ".join(f"{c}: {n} UFs" for c, n in cont.items()),
                       f"{apertada.uf} ({apertada.candidato}, margem de {_p(apertada.margem_pp)})".replace("%", " p.p.")])  # fmt: skip
    s.append(
        _tabela(linhas, ["Ano", "UFs vencidas no último turno (27)", "Disputa mais apertada"])
        + "\n"
    )

    # ---------------------------------------------------------- 3. municípios
    s.append("## 3. Municípios\n")
    vm = r["venc_mun"]
    vm = vm[vm["uf"] != "ZZ"]
    linhas = []
    for ano in anos:
        turno = vm.loc[vm["ano"] == ano, "turno"].max()
        d = vm[(vm["ano"] == ano) & (vm["turno"] == turno)]
        for cand, g in d.groupby("candidato"):
            linhas.append(
                [
                    ano,
                    cand,
                    _n(len(g)),
                    _p(100 * (g["pct_validos"] >= 70).mean()),
                    _p(g["pct_validos"].median()),
                ]
            )
    s.append(
        _tabela(
            linhas,
            [
                "Ano",
                "Vencedor no município",
                "Municípios",
                "% deles com ≥ 70% dos válidos",
                "% mediano do vencedor",
            ],
        )
        + "\n"
    )
    s.append(f"![Distribuição municipal](figuras/{figs['distribuicao']})\n")

    turnos = r["turnos"]
    if len(turnos):
        s.append("### Do 1º para o 2º turno\n")
        s.append(
            "Cada ponto é um município. Pontos acima da diagonal são lugares onde o candidato cresceu entre os turnos. "
            "A tabela mostra o crescimento mediano de cada finalista e em quantos municípios ele cresceu.\n"
        )
        linhas = []
        for (ano, cand), g in turnos.groupby(["ano", "candidato"]):
            linhas.append(
                [ano, cand, _pp(g["ganho_pp"].median()), _p(100 * (g["ganho_pp"] > 0).mean())]
            )
        s.append(
            _tabela(
                linhas,
                ["Ano", "Finalista", "Ganho mediano 1º→2º", "% dos municípios em que cresceu"],
            )
            + "\n"
        )
        for ano in sorted(turnos["ano"].unique()):
            if f"turnos_{ano}" in figs:
                s.append(f"![Entre turnos {ano}](figuras/{figs[f'turnos_{ano}']})\n")

    comp = r["comparacao"]
    if len(comp):
        a, b = anos[0], anos[-1]
        s.append(f"### {a} × {b}\n")
        s.append(
            f"Partidos que estiveram no último turno nos dois anos, comparados município a município "
            f"(arquivo [`comparacao_{a}_{b}_municipio.csv.gz`](../dados/resultados/comparacao_{a}_{b}_municipio.csv.gz)).\n"
        )
        for partido, g in comp.groupby("partido"):
            ca, cb = g[f"candidato_{a}"].iloc[0], g[f"candidato_{b}"].iloc[0]
            cresce = (g["variacao_pp"] > 0).mean() * 100
            vira = ((g[f"pct_validos_{a}"] < 50) & (g[f"pct_validos_{b}"] > 50)).sum()
            perde = ((g[f"pct_validos_{a}"] > 50) & (g[f"pct_validos_{b}"] < 50)).sum()
            s.append(
                f"- **{partido}** ({ca} em {a} → {cb} em {b}): variação mediana de {_pp(g['variacao_pp'].median())} por município; "
                f"cresceu em {_p(cresce)} dos municípios; passou a vencer em {_n(vira)} e deixou de vencer em {_n(perde)}.\n"
            )
            top = g.reindex(g["variacao_pp"].abs().sort_values(ascending=False).index).head(5)
            s.append(_tabela([[x.municipio.title(), x.uf, _p(getattr(x, f"pct_validos_{a}")), _p(getattr(x, f"pct_validos_{b}")), _pp(x.variacao_pp)]
                              for x in top.itertuples()], ["Maiores mudanças", "UF", str(a), str(b), "Variação"]) + "\n")  # fmt: skip
            chave = f"comparacao_{partido}"
            if chave in figs:
                s.append(f"![Comparação {partido}](figuras/{figs[chave]})\n")

    # ---------------------------------------------------------- 4. participação
    s.append("## 4. Comparecimento, abstenção, brancos e nulos\n")
    pb = r["part_br"]
    s.append(_tabela([[x.ano, f"{x.turno}º", _n(x.aptos), _n(x.comparecimento), _p(x.pct_abstencao), _p(x.pct_brancos), _p(x.pct_nulos)]
                      for x in pb.itertuples()], ["Ano", "Turno", "Aptos", "Compareceram", "Abstenção", "Brancos*", "Nulos*"]) + "\n")  # fmt: skip
    s.append("\\* em % dos votos registrados (comparecimento).\n")
    pu = r["part_uf"]
    pu = pu[(pu["uf"] != "ZZ") & (pu["turno"] == 1)]
    ult = pu[pu["ano"] == anos[-1]].sort_values("pct_abstencao")
    s.append(
        f"Em {anos[-1]}, no 1º turno, a menor abstenção foi em **{ult.iloc[0].uf}** ({_p(ult.iloc[0].pct_abstencao)}) e a maior em "
        f"**{ult.iloc[-1].uf}** ({_p(ult.iloc[-1].pct_abstencao)}). O exterior fica de fora do gráfico porque a abstenção "
        "lá é estruturalmente muito maior.\n"
    )
    s.append(f"![Abstenção por UF](figuras/{figs['abstencao']})\n")

    # ---------------------------------------------------------- 5. candidaturas
    s.append("## 5. Quem se candidata e quem se elege\n")
    s.append(
        "Todas as candidaturas aptas a presidente, governador, senador e deputados federais, estaduais e distritais "
        "(distritais somados aos estaduais). Cor/raça é autodeclarada no registro da candidatura; o percentual de "
        "pessoas negras (pretas + pardas) é calculado sobre quem informou.\n"
    )
    pf = r["perfil"]
    s.append(_tabela([[x.ano, x.cargo.title(), _n(x.candidaturas), _n(x.eleitos), _p(x.pct_mulheres_candidaturas), _p(x.pct_mulheres_eleitos),
                       _p(x.pct_negros_candidaturas), _p(x.pct_negros_eleitos), "–" if pd.isna(x.idade_mediana_eleitos) else int(x.idade_mediana_eleitos)]
                      for x in pf.itertuples()],
                     ["Ano", "Cargo", "Candidaturas", "Eleitos", "Mulheres (cand.)", "Mulheres (eleitas)", "Negros (cand.)", "Negros (eleitos)", "Idade mediana eleitos"]) + "\n")  # fmt: skip
    s.append(f"![Perfil das candidaturas](figuras/{figs['perfil']})\n")

    inst = r["instrucao"]
    ult = inst[inst["ano"] == anos[-1]].sort_values("taxa_sucesso", ascending=False)
    s.append(f"**Escolaridade ({anos[-1]})** — taxa de sucesso = eleitos ÷ candidaturas aptas.\n")
    s.append(_tabela([[x.instrucao.title() if isinstance(x.instrucao, str) else "Não informado", _n(x.candidaturas), _n(x.eleitos),
                       _p(x.pct_eleitos), _p(x.taxa_sucesso)] for x in ult.itertuples()],
                     ["Grau de instrução", "Candidaturas", "Eleitos", "% dos eleitos", "Taxa de sucesso"]) + "\n")  # fmt: skip

    # ---------------------------------------------------------- fontes
    s.append("## Fontes e reprodutibilidade\n")
    s.append(
        "Arquivos originais baixados nesta execução (o SHA-256 permite conferir que são os mesmos do TSE). "
        "Os .zip completos ficam disponíveis para download como *artifact* da execução do workflow no GitHub Actions.\n"
    )
    s.append(_tabela([[f["ano"], f["conjunto"], f"[{f['arquivo']}]({f['url']})", f"{f['bytes'] / 1e6:.1f} MB", f"`{f['sha256'][:16]}…`"]
                      for f in r["resumo"]["fontes"]], ["Ano", "Conjunto", "Arquivo", "Tamanho", "SHA-256"]) + "\n")  # fmt: skip
    s.append(
        "Observações metodológicas: votos de presidente somados por município a partir dos arquivos por município e zona "
        "(`votacao_candidato_munzona`); percentuais sobre votos válidos (exclui brancos e nulos), como na divulgação "
        "oficial; o código de município é o do TSE (não o do IBGE); `ZZ` = votos no exterior.\n"
    )
    cfg.relatorio.mkdir(parents=True, exist_ok=True)
    (cfg.relatorio / "RELATORIO.md").write_text("\n".join(s), encoding="utf-8")
