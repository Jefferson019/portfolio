"""Orquestra: download (bronze) -> extração padronizada (prata) -> análise (resultados + relatório)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from . import analise, graficos, leitura
from .config import Config
from .fontes import baixar, url_arquivo
from .relatorio import escrever_relatorio
from .util import ler_tabela, log, salvar_tabela

EXTRATORES = {
    "votacao_candidato_munzona": ("votacao_presidente", leitura.votacao_presidente),
    "detalhe_votacao_munzona": ("detalhe_presidente", leitura.detalhe_presidente),
    "consulta_cand": ("candidaturas", leitura.candidaturas),
}


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def extrair(cfg: Config, refazer: bool = False) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    tabelas: dict[str, list[pd.DataFrame]] = {nome: [] for nome, _ in EXTRATORES.values()}
    fontes = []
    for ano in cfg.anos:
        for conjunto, (nome, extrator) in EXTRATORES.items():
            zip_ = baixar(cfg, conjunto, ano)
            fontes.append(
                {
                    "conjunto": conjunto,
                    "ano": ano,
                    "url": url_arquivo(cfg, conjunto, ano),
                    "arquivo": zip_.name,
                    "bytes": zip_.stat().st_size,
                    "sha256": _sha256(zip_),
                }
            )
            destino = cfg.prata / f"{nome}_{ano}"
            df = None if refazer else ler_tabela(destino)
            if df is None:
                log.info("Extraindo %s (%s)", zip_.name, nome)
                df = extrator(zip_)
                salvar_tabela(df, destino)
            tabelas[nome].append(df)
    return {nome: pd.concat(partes, ignore_index=True) for nome, partes in tabelas.items()}, fontes


def _csv(df: pd.DataFrame, cfg: Config, nome: str) -> None:
    cfg.resultados.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(cfg.resultados / nome, index=False)


def analisar(cfg: Config, prata: dict[str, pd.DataFrame], fontes: list[dict]) -> dict:
    votos, detalhe, cand = (
        prata["votacao_presidente"],
        prata["detalhe_presidente"],
        prata["candidaturas"],
    )
    anos = sorted(votos["ano"].unique())

    nacional = analise.resultado(votos, [])
    regiao = analise.resultado(votos, ["regiao"])
    por_uf = analise.resultado(votos, ["uf", "regiao"])
    municipal = analise.resultado(votos, ["uf", "cd_municipio", "municipio"])
    venc_mun = analise.vencedores(municipal, ["uf", "cd_municipio", "municipio"])
    venc_uf = analise.vencedores(por_uf, ["uf", "regiao"])
    conf = analise.conferencia(nacional)

    part_br = analise.participacao(detalhe, [])
    part_uf = analise.participacao(detalhe, ["uf", "regiao"])
    part_mun = analise.participacao(detalhe, ["uf", "cd_municipio", "municipio"])

    turnos = analise.entre_turnos(municipal, nacional)
    comparacao = (
        analise.comparacao_anos(municipal, anos[0], anos[-1]) if len(anos) > 1 else pd.DataFrame()
    )

    perfil = analise.perfil_candidaturas(cand)
    instrucao = analise.instrucao_eleitos(cand)

    for df, nome in [
        (nacional, "presidente_brasil.csv"),
        (regiao, "presidente_regiao.csv"),
        (por_uf, "presidente_uf.csv"),
        (municipal, "presidente_municipio.csv.gz"),
        (venc_mun, "presidente_vencedor_municipio.csv.gz"),
        (conf, "conferencia_tse.csv"),
        (part_br, "participacao_brasil.csv"),
        (part_uf, "participacao_uf.csv"),
        (part_mun, "participacao_municipio.csv.gz"),
        (turnos, "entre_turnos_municipio.csv.gz"),
        (comparacao, f"comparacao_{anos[0]}_{anos[-1]}_municipio.csv.gz"),
        (perfil, "perfil_candidaturas.csv"),
        (instrucao, "instrucao_candidaturas.csv"),
    ]:
        if len(df):
            _csv(df, cfg, nome)

    # ---- gráficos
    figuras = cfg.relatorio / "figuras"
    cores = graficos.Cores(pd.concat([analise.finalistas(nacional, ano) for ano in anos]))
    figs: dict[str, str] = {}
    for ano in anos:
        figs[f"uf_{ano}"] = graficos.resultado_por_uf(
            por_uf, ano, cores, figuras / f"resultado_uf_{ano}.png"
        ).name
    figs["distribuicao"] = graficos.distribuicao_municipal(
        venc_mun, cores, figuras / "distribuicao_municipios.png"
    ).name
    for ano in sorted(turnos["ano"].unique()) if len(turnos) else []:
        fin = analise.finalistas(nacional, ano).iloc[0]
        d = turnos[(turnos["ano"] == ano) & (turnos["partido"] == fin["partido"])]
        figs[f"turnos_{ano}"] = graficos.dispersao(
            d, "pct_1t", "pct_2t", "% no 1º turno", "% no 2º turno",
            f"{fin['candidato']} ({ano}): 1º × 2º turno, por município",
            cores(fin["partido"], fin["candidato"]), figuras / f"entre_turnos_{ano}.png",
        ).name  # fmt: skip
    if len(comparacao):
        for partido, d in comparacao.groupby("partido"):
            figs[f"comparacao_{partido}"] = graficos.dispersao(
                d, f"pct_validos_{anos[0]}", f"pct_validos_{anos[-1]}",
                f"% em {anos[0]} ({d[f'candidato_{anos[0]}'].iloc[0]})",
                f"% em {anos[-1]} ({d[f'candidato_{anos[-1]}'].iloc[0]})",
                f"{partido}: último turno de {anos[0]} × {anos[-1]}, por município",
                cores(partido), figuras / f"comparacao_{partido}_{anos[0]}_{anos[-1]}.png",
            ).name  # fmt: skip
    figs["abstencao"] = graficos.abstencao_por_uf(part_uf, figuras / "abstencao_uf.png").name
    figs["perfil"] = graficos.perfil(
        perfil, anos[-1], figuras / f"perfil_candidaturas_{anos[-1]}.png"
    ).name

    resumo = {
        "gerado_em": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "anos": [int(a) for a in anos],
        "fontes": fontes,
        "conferencia_ok": bool(conf["confere"].all()) if len(conf) else None,
        "linhas": {
            "votacao_presidente": len(votos),
            "detalhe_presidente": len(detalhe),
            "candidaturas": len(cand),
        },
    }
    (cfg.resultados / "fontes_e_execucao.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    escrever_relatorio(
        cfg,
        dict(
            anos=anos, nacional=nacional, regiao=regiao, venc_uf=venc_uf, venc_mun=venc_mun, conf=conf,
            part_br=part_br, part_uf=part_uf, turnos=turnos, comparacao=comparacao, perfil=perfil,
            instrucao=instrucao, figs=figs, resumo=resumo,
        ),
    )  # fmt: skip
    return resumo


def executar(cfg: Config, refazer: bool = False) -> dict:
    prata, fontes = extrair(cfg, refazer=refazer)
    resumo = analisar(cfg, prata, fontes)
    log.info("Concluído. Resultados em %s e relatório em %s", cfg.resultados, cfg.relatorio)
    if resumo["conferencia_ok"] is False:
        log.warning(
            "Há divergências na conferência com os resultados oficiais; veja conferencia_tse.csv"
        )
    return resumo
