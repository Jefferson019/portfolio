"""Orquestração do pipeline: download -> bronze -> prata -> ouro -> conciliação -> painel."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd

from . import beneficiarios, cadastro, conciliacao, contabil, indicadores, mercado, painel
from .config import Config
from .fontes import ClienteANS
from .util import log, periodo


def _salvar_tabela(df: pd.DataFrame, destino_sem_extensao: Path) -> None:
    destino_sem_extensao.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino_sem_extensao.with_suffix(".csv.gz"), index=False, compression="gzip")
    try:  # Parquet é opcional (pip install "observatorio-ans[parquet]") e nunca interrompe o pipeline
        df.to_parquet(destino_sem_extensao.with_suffix(".parquet"), index=False)
    except ImportError:
        pass
    except Exception as erro:
        log.warning("Parquet não gerado para %s: %s", destino_sem_extensao.name, erro)


def _arquivos_locais(
    dir_bronze: Path, ano_inicio: int, ano_fim: int | None
) -> list[tuple[int, int, Path]]:
    """Modo offline: usa os zips já presentes em dados/bronze/demonstracoes_contabeis/."""
    achados = []
    for caminho in sorted((dir_bronze / "demonstracoes_contabeis").rglob("*.zip")):
        m = re.search(r"([1-4])T(\d{4})", caminho.name, re.IGNORECASE)
        if not m:
            continue
        ano, tri = int(m.group(2)), int(m.group(1))
        if ano >= ano_inicio and (ano_fim is None or ano <= ano_fim):
            achados.append((ano, tri, caminho))
    return sorted(achados)


def executar(
    cfg: Config,
    sem_download: bool = False,
    sem_beneficiarios: bool = False,
    forcar_download: bool = False,
) -> dict:
    inicio = time.time()
    cliente = ClienteANS(cfg.url_base, permitir_http=cfg.permitir_http)
    qualidade: dict = {"fonte": cfg.url_base, "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S")}

    # ------------------------------------------------------------------ 1. bronze (downloads)
    if sem_download:
        arquivos = _arquivos_locais(cfg.dir_bronze, cfg.ano_inicio, cfg.ano_fim)
        cad_ativas = cfg.dir_bronze / "cadop" / "Relatorio_cadop.csv"
        cad_canceladas = cfg.dir_bronze / "cadop" / "Relatorio_cadop_canceladas.csv"
        if not arquivos:
            raise FileNotFoundError(
                f"Modo offline: nenhum zip trimestral em {cfg.dir_bronze / 'demonstracoes_contabeis'}"
            )
        if not cad_ativas.exists():
            raise FileNotFoundError(f"Modo offline: falta {cad_ativas}")
    else:
        arquivos = contabil.baixar_trimestres(
            cliente, cfg.dir_bronze, cfg.ano_inicio, cfg.ano_fim, forcar_download
        )
        cad_ativas, cad_canceladas = cadastro.baixar_cadastro(cliente, cfg.dir_bronze)
    if not arquivos:
        raise RuntimeError("Nenhum arquivo de demonstrações contábeis encontrado")

    # ------------------------------------------------------------------ 2. prata
    qualidade["leitura"] = contabil.bronze_para_prata(arquivos, cfg.dir_prata)
    cad = cadastro.montar_cadastro(cad_ativas, cad_canceladas)
    _salvar_tabela(cad, cfg.dir_prata / "operadoras")

    if sem_beneficiarios or sem_download:
        hist_op, hist_uf = beneficiarios.carregar_historico(cfg.dir_historico)
    else:
        hist_op, hist_uf = beneficiarios.atualizar_historico(
            cliente, cfg.dir_bronze, cfg.dir_historico, cfg.beneficiarios_trimestres
        )
    qualidade["beneficiarios_competencias"] = sorted(hist_op["competencia"].unique().tolist())

    # ------------------------------------------------------------------ 3. ouro
    periodos = [(a, t) for a, t, _ in arquivos]
    conceitos, qualidade["conceitos"] = contabil.montar_conceitos(cfg.dir_prata, periodos)
    modos = contabil.detectar_modo_acumulacao(conceitos)
    qualidade["acumulacao"] = {str(k): v for k, v in modos.items()}
    janelas = contabil.calcular_janelas(conceitos, modos)

    base_ops = indicadores.montar_operadoras(janelas, cad)
    base_ops = beneficiarios.anexar_beneficiarios(base_ops, hist_op)

    referencias = conciliacao.carregar_referencias()
    ops = indicadores.finalizar_operadoras(base_ops, "bruta")
    merc = mercado.agregar_mercado(ops, "bruta")
    if cfg.sinistralidade == "auto":
        variante, escolha = conciliacao.escolher_variante_sinistralidade(merc, referencias)
    else:
        variante, escolha = cfg.sinistralidade, {"motivo": "definida em projeto.toml"}
    qualidade["sinistralidade"] = {"variante": variante, **escolha}
    if variante != "bruta":
        ops = indicadores.finalizar_operadoras(base_ops, variante)
        merc = mercado.agregar_mercado(ops, variante)
    log.info("Sinistralidade: variante '%s' (%s)", variante, escolha.get("motivo"))

    ultimo_periodo = periodo(*max(periodos))
    recente = ops[(ops["periodo"] == ultimo_periodo) & (ops["janela"] == "acumulado_ano")]
    sem_cadastro = recente[recente["segmento"] == "nao_identificado"]
    receita = recente["receita_contraprestacoes"].sum()
    qualidade["operadoras_sem_cadastro"] = {
        "periodo": ultimo_periodo,
        "quantidade": int(len(sem_cadastro)),
        "participacao_receita": round(
            float(sem_cadastro["receita_contraprestacoes"].sum() / receita), 6
        )
        if receita
        else None,
        "registros": sem_cadastro["reg_ans"].head(20).tolist(),
    }

    conc = conciliacao.conciliar(merc, referencias)
    qualidade["conciliacao"] = conc["status"].value_counts().to_dict() if not conc.empty else {}

    _salvar_tabela(ops, cfg.dir_ouro / "operadoras_indicadores")
    _salvar_tabela(merc, cfg.dir_ouro / "mercado_indicadores")
    conc.to_csv(cfg.dir_ouro / "conciliacao_ans.csv", index=False)

    ultimo = max(periodos)
    meta = {
        "periodo_mais_recente": periodo(*ultimo),
        "variante_sinistralidade": variante,
        "n_trimestres": len(periodos),
        "primeiro_periodo": periodo(*min(periodos)),
    }
    qualidade.update(meta)
    qualidade["duracao_segundos"] = round(time.time() - inicio, 1)
    (cfg.dir_ouro / "relatorio_qualidade.json").write_text(
        json.dumps(qualidade, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )

    # ------------------------------------------------------------------ 4. painel
    painel.gerar_painel(cfg, ops, merc, conc, hist_op, hist_uf, meta)
    log.info("Concluído em %.0fs. Painel em %s", time.time() - inicio, cfg.dir_site / "index.html")
    return qualidade


def regerar_painel(cfg: Config) -> None:
    """Recria o painel a partir das tabelas da camada ouro (sem baixar nem recalcular nada)."""
    leitura = {"reg_ans": str, "periodo": str, "valor": str}
    ops = pd.read_csv(
        cfg.dir_ouro / "operadoras_indicadores.csv.gz", dtype=leitura, low_memory=False
    )
    merc = pd.read_csv(cfg.dir_ouro / "mercado_indicadores.csv.gz", dtype=leitura, low_memory=False)
    conc = pd.read_csv(cfg.dir_ouro / "conciliacao_ans.csv", dtype={"periodo": str})
    qualidade = json.loads((cfg.dir_ouro / "relatorio_qualidade.json").read_text(encoding="utf-8"))
    hist_op, hist_uf = beneficiarios.carregar_historico(cfg.dir_historico)
    meta = {
        k: qualidade[k]
        for k in (
            "periodo_mais_recente",
            "variante_sinistralidade",
            "n_trimestres",
            "primeiro_periodo",
        )
    }
    painel.gerar_painel(cfg, ops, merc, conc, hist_op, hist_uf, meta)
