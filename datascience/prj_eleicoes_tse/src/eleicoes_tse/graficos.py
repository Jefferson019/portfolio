"""Gráficos estáticos (PNG) do relatório, com a mesma paleta e anatomia em todos."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# Paleta categórica validada (ordem fixa) e tintas de texto/eixos
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
MUDO = "#898781"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"

plt.rcParams.update(
    {
        "figure.facecolor": SUPERFICIE,
        "axes.facecolor": SUPERFICIE,
        "savefig.facecolor": SUPERFICIE,
        "font.family": "sans-serif",
        "font.size": 10,
        "text.color": TINTA,
        "axes.labelcolor": TINTA_2,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.edgecolor": EIXO,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRADE,
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "xtick.color": MUDO,
        "ytick.color": MUDO,
        "xtick.labelcolor": TINTA_2,
        "ytick.labelcolor": TINTA_2,
        "legend.frameon": False,
    }
)


def identidades(finalistas: pd.DataFrame) -> dict[tuple[str, str], str]:
    """(partido, candidato) -> identidade visual. Quem disputou mais de um ano mantém a própria cor
    (ex.: o mesmo candidato por partidos diferentes); os demais herdam a cor do partido."""
    repetidos = finalistas.groupby("candidato")["ano"].nunique()
    repetidos = set(repetidos[repetidos > 1].index)
    return {
        (x.partido, x.candidato): (x.candidato if x.candidato in repetidos else x.partido)
        for x in finalistas.itertuples()
    }


def paleta(chaves: list[str]) -> dict[str, str]:
    """A cor acompanha a identidade em todos os gráficos e anos (nunca a posição)."""
    return {c: SERIES[i % len(SERIES)] for i, c in enumerate(dict.fromkeys(chaves))}


class Cores:
    def __init__(self, finalistas: pd.DataFrame):
        self.ident = identidades(finalistas)
        self.cor = paleta(list(self.ident.values()))

    def __call__(self, partido: str, candidato: str | None = None) -> str:
        chave = self.ident.get((partido, candidato)) if candidato else None
        if chave is None:
            chave = next((v for (p, _), v in self.ident.items() if p == partido), partido)
        return self.cor.get(chave, MUDO)


def _salvar(fig, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return destino


def resultado_por_uf(por_uf: pd.DataFrame, ano: int, cores: Cores, destino: Path) -> Path:
    """% dos válidos do 1º colocado nacional em cada UF, no último turno; cor = quem venceu na UF."""
    d = por_uf[por_uf["ano"] == ano]
    d = d[d["turno"] == d["turno"].max()]
    turno = int(d["turno"].iloc[0])
    nacional = d.groupby("partido")["votos"].sum().sort_values(ascending=False)
    lider, segundo = nacional.index[0], nacional.index[1]
    nomes = d.drop_duplicates("partido").set_index("partido")["candidato"]
    serie = d[d["partido"] == lider].set_index("uf")["pct_validos"].sort_values()
    vencedor_uf = d[d["posicao"] == 1].set_index("uf")["partido"]

    fig, ax = plt.subplots(figsize=(7.5, max(4, 0.3 * len(serie) + 1.5)))
    rotulos = [("Exterior" if uf == "ZZ" else uf) for uf in serie.index]
    barras = ax.barh(
        rotulos,
        serie.values,
        height=0.7,
        color=[cores(vencedor_uf[uf], nomes[vencedor_uf[uf]]) for uf in serie.index],
    )
    for barra, valor in zip(barras, serie.values, strict=True):
        ax.text(
            valor + 0.8,
            barra.get_y() + barra.get_height() / 2,
            f"{valor:.1f}%",
            va="center",
            fontsize=8,
            color=TINTA_2,
        )
    ax.axvline(50, color=TINTA_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(
        50.5, 0.995, "50%", color=TINTA_2, fontsize=8, va="top", transform=ax.get_xaxis_transform()
    )
    ax.set_xlim(0, 100)
    ax.set_xlabel(f"% dos votos válidos de {nomes[lider]} ({lider})")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Presidente {ano}, {turno}º turno: votação de {nomes[lider]} por UF")
    handles = [plt.Rectangle((0, 0), 1, 1, color=cores(p, nomes[p])) for p in (lider, segundo)]
    ax.legend(
        handles,
        [f"{nomes[p]} venceu na UF" for p in (lider, segundo)],
        loc="lower right",
        fontsize=8,
    )
    return _salvar(fig, destino)


def distribuicao_municipal(venc_mun: pd.DataFrame, cores: Cores, destino: Path) -> Path:
    """Histograma empilhado da % do vencedor em cada município, um painel por ano (último turno)."""
    anos = sorted(venc_mun["ano"].unique())
    fig, eixos = plt.subplots(
        1, len(anos), figsize=(5.2 * len(anos), 3.8), sharey=True, squeeze=False
    )
    for ax, ano in zip(eixos[0], anos, strict=True):
        d = venc_mun[venc_mun["ano"] == ano]
        d = d[(d["turno"] == d["turno"].max()) & (d["uf"] != "ZZ")]
        grupos = sorted(d.groupby(["partido", "candidato"]), key=lambda kv: -len(kv[1]))
        ax.hist(
            [g["pct_validos"] for _, g in grupos],
            bins=range(50, 101, 2),
            stacked=True,
            color=[cores(p, c) for (p, c), _ in grupos],
            edgecolor=SUPERFICIE,
            linewidth=1,
            label=[f"{c} venceu ({len(g):,} mun.)".replace(",", ".") for (_, c), g in grupos],
        )
        ax.set_title(f"{ano}", pad=8)
        ax.set_xlabel("% dos válidos do vencedor no município")
        ax.grid(axis="x", visible=False)
        ax.legend(fontsize=8, loc="upper right")
    eixos[0][0].set_ylabel("municípios")
    fig.suptitle(
        "Quão folgada foi a vitória em cada município (último turno)",
        x=0.01,
        y=1.04,
        ha="left",
        fontweight="bold",
    )
    return _salvar(fig, destino)


def dispersao(
    df: pd.DataFrame,
    x: str,
    y: str,
    rotulo_x: str,
    rotulo_y: str,
    titulo: str,
    cor: str,
    destino: Path,
) -> Path:
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(df[x], df[y], s=8, color=cor, alpha=0.35, linewidths=0)
    ax.plot([0, 100], [0, 100], color=TINTA_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(97, 92, "sem mudança", color=TINTA_2, fontsize=8, ha="right")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel(rotulo_x)
    ax.set_ylabel(rotulo_y)
    ax.set_title(titulo)
    ax.set_aspect("equal")
    return _salvar(fig, destino)


def abstencao_por_uf(part_uf: pd.DataFrame, destino: Path) -> Path:
    """Abstenção por UF no 1º turno: um ponto por ano (o mais recente destacado)."""
    d = part_uf[(part_uf["turno"] == 1) & (part_uf["uf"] != "ZZ")]
    anos = sorted(d["ano"].unique())
    ultimo = anos[-1]
    ordem = d[d["ano"] == ultimo].sort_values("pct_abstencao")["uf"].tolist()
    fig, ax = plt.subplots(figsize=(7, 8))
    for ano in anos:
        s = d[d["ano"] == ano].set_index("uf").loc[ordem, "pct_abstencao"]
        destaque = ano == ultimo
        ax.scatter(
            s.values,
            ordem,
            s=36 if destaque else 28,
            color=SERIES[0] if destaque else MUDO,
            zorder=3,
            label=str(ano),
            edgecolors=SUPERFICIE,
            linewidths=1,
        )
    if len(anos) > 1:
        primeiro = d[d["ano"] == anos[0]].set_index("uf").loc[ordem, "pct_abstencao"]
        atual = d[d["ano"] == ultimo].set_index("uf").loc[ordem, "pct_abstencao"]
        ax.hlines(ordem, primeiro.values, atual.values, color=EIXO, linewidth=1.5, zorder=2)
    ax.set_xlabel("% dos eleitores aptos que não votaram")
    ax.grid(axis="y", visible=False)
    ax.set_title("Abstenção no 1º turno da eleição presidencial, por UF")
    ax.legend(loc="lower right")
    return _salvar(fig, destino)


def perfil(perfil_df: pd.DataFrame, ano: int, destino: Path) -> Path:
    """Mulheres e pessoas negras: candidaturas × eleitos, por cargo."""
    d = perfil_df[perfil_df["ano"] == ano].set_index("cargo")
    cargos = [c for c in d.index if d.loc[c, "eleitos"] > 0]
    d = d.loc[cargos]
    nomes = [c.title().replace("Deputado ", "Dep. ") for c in cargos]
    fig, eixos = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, (grupo, titulo) in zip(
        eixos,
        [("mulheres", "Mulheres"), ("negros", "Pessoas negras (pretas e pardas)")],
        strict=True,
    ):
        y = range(len(cargos))
        cand, eleitos = d[f"pct_{grupo}_candidaturas"], d[f"pct_{grupo}_eleitos"]
        ax.hlines(list(y), eleitos.values, cand.values, color=EIXO, linewidth=1.5, zorder=2)
        ax.scatter(
            cand.values,
            list(y),
            color=MUDO,
            s=36,
            zorder=3,
            label="entre candidaturas aptas",
            edgecolors=SUPERFICIE,
        )
        ax.scatter(
            eleitos.values,
            list(y),
            color=SERIES[0],
            s=36,
            zorder=3,
            label="entre eleitos",
            edgecolors=SUPERFICIE,
        )
        for yi, v, c in zip(y, eleitos.values, cand.values, strict=True):
            if pd.notna(v):
                lado = -1 if v < c else 1
                ax.text(
                    v + lado * 1.5,
                    yi,
                    f"{v:.0f}%",
                    color=TINTA_2,
                    fontsize=8,
                    va="center",
                    ha="right" if lado < 0 else "left",
                )
        ax.set_yticks(list(y), nomes)
        ax.set_xlim(-8, 75)
        ax.set_xlabel("%")
        ax.grid(axis="y", visible=False)
        ax.set_title(titulo)
    eixos[0].invert_yaxis()
    eixos[0].legend(loc="upper center", bbox_to_anchor=(1.1, -0.2), ncol=2, fontsize=9)
    fig.suptitle(
        f"Eleições {ano}: quem se candidata e quem se elege",
        x=0.01,
        y=1.04,
        ha="left",
        fontweight="bold",
    )
    return _salvar(fig, destino)
