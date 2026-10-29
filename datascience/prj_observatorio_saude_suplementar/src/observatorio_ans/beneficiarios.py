"""Beneficiários (informações consolidadas do SIB): totais por operadora, cobertura, contratação e UF.

Os arquivos mensais da ANS são grandes (centenas de MB por mês). Por isso o pipeline:
  * processa apenas os meses necessários (mês mais recente, fins de trimestre recentes e o mesmo
    mês do ano anterior);
  * guarda só agregados pequenos em `dados/historico/`, que podem ser versionados no Git;
  * em execuções seguintes, processa apenas meses novos.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .config import LIMITE_GRANDE_PORTE, LIMITE_PEQUENO_PORTE, PREFIXO_BENEFICIARIOS
from .fontes import ClienteANS
from .util import (
    inspecionar_csv,
    log,
    mapear_colunas,
    normalizar_coluna,
    normalizar_reg_ans,
    normalizar_texto,
    parse_valor_br,
)

ALIASES_SIB = {
    "REG_ANS": ["CD_OPERADORA", "REGISTRO_OPERADORA", "REG_ANS", "CD_OPERADO"],
    "UF": ["SG_UF", "UF"],
    "COBERTURA": ["COBERTURA_ASSIST_PLAN", "DE_COBERTURA_ASSIST_PLAN", "COBERTURA"],
    "CONTRATACAO": ["DE_CONTRATACAO_PLANO", "CONTRATACAO", "TP_CONTRATACAO"],
    "QTD": ["QT_BENEFICIARIO_ATIVO", "QT_BENEFICIARIOS_ATIVOS", "QT_BENEFICIARIO"],
}
ARQ_OPERADORA = "beneficiarios_operadora.csv.gz"
ARQ_UF = "beneficiarios_uf.csv.gz"


def _cobertura(valor: str) -> str:
    return "odontologico" if "ODONTO" in normalizar_texto(valor) else "medico_hospitalar"


def _contratacao(valor: str) -> str:
    t = normalizar_texto(valor)
    if "INDIVIDUAL" in t or "FAMILIAR" in t:
        return "individual"
    if "EMPRESARIAL" in t:
        return "coletivo_empresarial"
    if "ADESAO" in t:
        return "coletivo_adesao"
    return "outros"


# ============================================================================ descoberta


def pasta_beneficiarios(cliente: ClienteANS) -> str:
    for entrada in cliente.listar(""):
        if entrada.diretorio and entrada.nome.startswith(PREFIXO_BENEFICIARIOS):
            return entrada.nome + "/"
    raise RuntimeError(f"Pasta '{PREFIXO_BENEFICIARIOS}*' não encontrada no portal da ANS")


def meses_disponiveis(cliente: ClienteANS, pasta: str) -> list[str]:
    return sorted(
        e.nome for e in cliente.listar(pasta) if e.diretorio and re.fullmatch(r"\d{6}", e.nome)
    )


def escolher_meses(disponiveis: list[str], n_trimestres: int) -> list[str]:
    """Mês mais recente + últimos fins de trimestre + mesmo mês do ano anterior."""
    if not disponiveis:
        return []
    disponiveis = sorted(disponiveis)
    ultimo = disponiveis[-1]
    escolhidos = {ultimo}
    fins = [m for m in disponiveis if m[-2:] in {"03", "06", "09", "12"}]
    escolhidos.update(fins[-n_trimestres:] if n_trimestres > 0 else [])
    ano_anterior = f"{int(ultimo[:4]) - 1}{ultimo[4:]}"
    if ano_anterior in disponiveis:
        escolhidos.add(ano_anterior)
    return sorted(escolhidos)


# ============================================================================ processamento


def agregar_arquivo_sib(caminho_zip: Path) -> pd.DataFrame:
    """Agrega um zip mensal (uma UF) por operadora, cobertura, contratação e UF."""
    partes = []
    with zipfile.ZipFile(caminho_zip) as zf:
        for membro in [m for m in zf.namelist() if m.lower().endswith((".csv", ".txt"))]:
            encoding, sep, colunas = inspecionar_csv(lambda m=membro: zf.open(m))
            mapa = mapear_colunas(colunas, ALIASES_SIB)
            faltando = [c for c in ("REG_ANS", "QTD", "COBERTURA") if c not in mapa]
            if faltando:
                raise ValueError(
                    f"{caminho_zip.name}: colunas ausentes {faltando}. Encontradas: {colunas}"
                )
            desejadas = {normalizar_coluna(v) for v in mapa.values()}
            renomear = {normalizar_coluna(v): k for k, v in mapa.items()}
            with zf.open(membro) as f:
                leitor = pd.read_csv(
                    f,
                    sep=sep,
                    dtype=str,
                    encoding=encoding,
                    encoding_errors="replace",
                    keep_default_na=False,
                    chunksize=500_000,
                    usecols=lambda c, alvo=frozenset(desejadas): normalizar_coluna(c) in alvo,
                )
                for bloco in leitor:
                    bloco.columns = [renomear.get(normalizar_coluna(c), c) for c in bloco.columns]
                    if "UF" not in bloco:
                        bloco["UF"] = ""
                    if "CONTRATACAO" not in bloco:
                        bloco["CONTRATACAO"] = ""
                    cob = {v: _cobertura(v) for v in bloco["COBERTURA"].unique()}
                    con = {v: _contratacao(v) for v in bloco["CONTRATACAO"].unique()}
                    agregado = (
                        pd.DataFrame(
                            {
                                "reg_ans": normalizar_reg_ans(bloco["REG_ANS"]),
                                "cobertura": bloco["COBERTURA"].map(cob),
                                "contratacao": bloco["CONTRATACAO"].map(con),
                                "uf": bloco["UF"].str.strip().str.upper(),
                                "beneficiarios": parse_valor_br(bloco["QTD"]).fillna(0.0),
                            }
                        )
                        .dropna(subset=["reg_ans"])
                        .groupby(["reg_ans", "cobertura", "contratacao", "uf"], as_index=False)[
                            "beneficiarios"
                        ]
                        .sum()
                    )
                    partes.append(agregado)
    if not partes:
        return pd.DataFrame(columns=["reg_ans", "cobertura", "contratacao", "uf", "beneficiarios"])
    return (
        pd.concat(partes, ignore_index=True)
        .groupby(["reg_ans", "cobertura", "contratacao", "uf"], as_index=False)["beneficiarios"]
        .sum()
    )


def processar_mes(
    cliente: ClienteANS, pasta: str, competencia: str, dir_bronze: Path, manter_brutos: bool = False
) -> pd.DataFrame:
    entradas = [
        e for e in cliente.listar(f"{pasta}{competencia}/") if e.nome.lower().endswith(".zip")
    ]
    if not entradas:
        raise RuntimeError(f"Nenhum arquivo de beneficiários em {pasta}{competencia}/")
    partes = []
    for entrada in entradas:
        destino = dir_bronze / "beneficiarios" / competencia / entrada.nome
        caminho = cliente.baixar(entrada.url, destino)
        partes.append(agregar_arquivo_sib(caminho))
        if not manter_brutos:
            caminho.unlink(missing_ok=True)
            caminho.with_name(caminho.name + ".meta.json").unlink(missing_ok=True)
    df = pd.concat(partes, ignore_index=True)
    df = df.groupby(["reg_ans", "cobertura", "contratacao", "uf"], as_index=False)[
        "beneficiarios"
    ].sum()
    df.insert(0, "competencia", competencia)
    return df


def atualizar_historico(
    cliente: ClienteANS,
    dir_bronze: Path,
    dir_historico: Path,
    n_trimestres: int,
    forcar: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Processa os meses necessários que ainda não estão no histórico e devolve os agregados."""
    dir_historico.mkdir(parents=True, exist_ok=True)
    hist_op, hist_uf = carregar_historico(dir_historico)
    pasta = pasta_beneficiarios(cliente)
    meses = escolher_meses(meses_disponiveis(cliente, pasta), n_trimestres)
    ja_processados = set() if forcar else set(hist_op["competencia"].unique())
    novos = [m for m in meses if m not in ja_processados]
    log.info("Beneficiários: meses alvo %s; a processar %s", meses, novos or "nenhum")
    for competencia in novos:
        detalhe = processar_mes(cliente, pasta, competencia, dir_bronze)
        por_operadora = detalhe.groupby(
            ["competencia", "reg_ans", "cobertura", "contratacao"], as_index=False
        )["beneficiarios"].sum()
        por_uf = detalhe.groupby(["competencia", "uf", "cobertura"], as_index=False)[
            "beneficiarios"
        ].sum()
        hist_op = pd.concat(
            [hist_op[hist_op["competencia"] != competencia], por_operadora], ignore_index=True
        )
        hist_uf = pd.concat(
            [hist_uf[hist_uf["competencia"] != competencia], por_uf], ignore_index=True
        )
        # Salva a cada mês: se a execução cair, o trabalho feito não se perde
        salvar_historico(hist_op, hist_uf, dir_historico)
    return hist_op, hist_uf


def carregar_historico(dir_historico: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    op_path, uf_path = dir_historico / ARQ_OPERADORA, dir_historico / ARQ_UF
    tipos = {"competencia": str, "reg_ans": str, "uf": str}
    hist_op = (
        pd.read_csv(op_path, dtype=tipos, keep_default_na=False)
        if op_path.exists()
        else pd.DataFrame(
            columns=["competencia", "reg_ans", "cobertura", "contratacao", "beneficiarios"]
        )
    )
    hist_uf = (
        pd.read_csv(uf_path, dtype=tipos, keep_default_na=False)
        if uf_path.exists()
        else pd.DataFrame(columns=["competencia", "uf", "cobertura", "beneficiarios"])
    )
    for df in (hist_op, hist_uf):
        df["beneficiarios"] = pd.to_numeric(df["beneficiarios"], errors="coerce").fillna(0.0)
    return hist_op, hist_uf


def salvar_historico(hist_op: pd.DataFrame, hist_uf: pd.DataFrame, dir_historico: Path) -> None:
    hist_op.sort_values(["competencia", "reg_ans", "cobertura", "contratacao"]).to_csv(
        dir_historico / ARQ_OPERADORA, index=False, compression="gzip"
    )
    hist_uf.sort_values(["competencia", "uf", "cobertura"]).to_csv(
        dir_historico / ARQ_UF, index=False, compression="gzip"
    )


# ============================================================================ porte e totais


def classificar_porte(beneficiarios: pd.Series) -> pd.Series:
    b = pd.to_numeric(beneficiarios, errors="coerce")
    porte = pd.Series("sem_informacao", index=b.index, dtype=object)
    porte[b <= 0] = "sem_beneficiarios"
    porte[(b > 0) & (b < LIMITE_PEQUENO_PORTE)] = "pequeno"
    porte[(b >= LIMITE_PEQUENO_PORTE) & (b <= LIMITE_GRANDE_PORTE)] = "medio"
    porte[b > LIMITE_GRANDE_PORTE] = "grande"
    return porte


def totais_por_operadora(hist_op: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por competência e operadora com beneficiários médico-hospitalares e odontológicos."""
    if hist_op.empty:
        return pd.DataFrame(columns=["competencia", "reg_ans", "benef_medico", "benef_odonto"])
    tab = hist_op.pivot_table(
        index=["competencia", "reg_ans"],
        columns="cobertura",
        values="beneficiarios",
        aggfunc="sum",
        fill_value=0.0,
    )
    tab = tab.rename(columns={"medico_hospitalar": "benef_medico", "odontologico": "benef_odonto"})
    for c in ("benef_medico", "benef_odonto"):
        if c not in tab:
            tab[c] = 0.0
    return tab[["benef_medico", "benef_odonto"]].reset_index()


def competencia_do_trimestre(ano: int, tri: int) -> str:
    return f"{int(ano)}{int(tri) * 3:02d}"


def media_movel_trimestral(totais: pd.DataFrame, ano: int, tri: int) -> pd.DataFrame:
    """Média de beneficiários nos fins de trimestre da janela de 12 meses que termina em (ano, tri)."""
    comps = []
    a, t = ano, tri
    for _ in range(4):
        comps.append(competencia_do_trimestre(a, t))
        t -= 1
        if t == 0:
            a, t = a - 1, 4
    sub = totais[totais["competencia"].isin(comps)]
    if sub.empty:
        return pd.DataFrame(columns=["reg_ans", "benef_medico_medio", "benef_odonto_medio"])
    media = sub.groupby("reg_ans")[["benef_medico", "benef_odonto"]].mean()
    return media.add_suffix("_medio").reset_index()


def anexar_beneficiarios(ops: pd.DataFrame, hist_op: pd.DataFrame) -> pd.DataFrame:
    """Anexa beneficiários do fim do trimestre, média de 12 meses e porte a cada linha de operadora."""
    ops = ops.copy()
    totais = totais_por_operadora(hist_op)
    if totais.empty:
        for c in (
            "benef_medico",
            "benef_odonto",
            "benef_medico_medio",
            "benef_odonto_medio",
            "beneficiarios",
        ):
            ops[c] = np.nan
        ops["porte"] = "sem_informacao"
        return ops

    ops["competencia"] = [
        competencia_do_trimestre(a, t) for a, t in zip(ops["ano"], ops["tri"], strict=True)
    ]
    ops = ops.merge(totais, on=["competencia", "reg_ans"], how="left")

    # Média dos fins de trimestre (para indicadores por beneficiário na janela de 12 meses)
    medias = []
    for (ano, tri), _ in ops.groupby(["ano", "tri"]):
        m = media_movel_trimestral(totais, int(ano), int(tri))
        if not m.empty:
            medias.append(m.assign(ano=ano, tri=tri))
    if medias:
        ops = ops.merge(
            pd.concat(medias, ignore_index=True), on=["reg_ans", "ano", "tri"], how="left"
        )
    else:
        ops["benef_medico_medio"] = np.nan
        ops["benef_odonto_medio"] = np.nan

    # Competência mais recente disponível: usada quando o fim do trimestre não foi processado
    ultimo = totais["competencia"].max()
    recente = totais[totais["competencia"] == ultimo].drop(columns="competencia")
    recente = recente.rename(
        columns={"benef_medico": "benef_medico_atual", "benef_odonto": "benef_odonto_atual"}
    )
    ops = ops.merge(recente, on="reg_ans", how="left")

    odonto = ops["segmento"].eq("odontologico")
    ref_periodo = np.where(odonto, ops["benef_odonto"], ops["benef_medico"])
    ref_atual = np.where(odonto, ops["benef_odonto_atual"], ops["benef_medico_atual"])
    ops["beneficiarios"] = np.where(ops["segmento"].eq("administradora"), np.nan, ref_periodo)
    base_porte = pd.Series(np.where(pd.isna(ref_periodo), ref_atual, ref_periodo), index=ops.index)
    # Operadora presente no cadastro mas sem registro no SIB = sem beneficiários
    ops["porte"] = classificar_porte(base_porte)
    ops.loc[ops["segmento"].eq("administradora"), "porte"] = "nao_se_aplica"
    return ops.drop(columns=["competencia", "benef_medico_atual", "benef_odonto_atual"])
