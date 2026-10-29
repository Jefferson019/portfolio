"""Cadastro de operadoras (CADOP): ativas e canceladas, com modalidade e segmento padronizados."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import (
    CAMINHO_CADOP_ATIVAS,
    CAMINHO_CADOP_CANCELADAS,
    MODALIDADE_NAO_IDENTIFICADA,
    MODALIDADES,
)
from .fontes import ClienteANS
from .util import ler_csv_texto, log, mapear_colunas, normalizar_reg_ans, normalizar_texto

ALIASES_CADOP = {
    "REG_ANS": ["REGISTRO_OPERADORA", "REGISTRO_ANS", "REG_ANS", "CD_OPERADORA"],
    "CNPJ": ["CNPJ"],
    "RAZAO_SOCIAL": ["RAZAO_SOCIAL"],
    "NOME_FANTASIA": ["NOME_FANTASIA"],
    "MODALIDADE": ["MODALIDADE"],
    "CIDADE": ["CIDADE", "MUNICIPIO"],
    "UF": ["UF"],
    "DATA_REGISTRO": ["DATA_REGISTRO_ANS"],
    "DATA_CANCELAMENTO": ["DATA_DESCREDENCIAMENTO", "DATA_CANCELAMENTO"],
    "MOTIVO_CANCELAMENTO": ["MOTIVO_DO_DESCREDENCIAMENTO", "MOTIVO_DESCREDENCIAMENTO"],
}

# Trechos (sem acento, maiúsculas) que identificam cada modalidade; a ordem importa
_REGRAS_MODALIDADE = [
    ("ODONTOLOGIA DE GRUPO", "Odontologia de Grupo"),
    ("COOPERATIVA ODONTO", "Cooperativa Odontológica"),
    ("COOPERATIVA MEDICA", "Cooperativa Médica"),
    ("MEDICINA DE GRUPO", "Medicina de Grupo"),
    ("SEGURADORA", "Seguradora Especializada em Saúde"),
    ("AUTOGEST", "Autogestão"),
    ("FILANTROP", "Filantropia"),
    ("ADMINISTRADORA", "Administradora de Benefícios"),
]


def padronizar_modalidade(valor: object) -> str:
    texto = normalizar_texto(valor)
    for trecho, nome in _REGRAS_MODALIDADE:
        if trecho in texto:
            return nome
    return MODALIDADE_NAO_IDENTIFICADA


def segmento_da_modalidade(modalidade: str) -> str:
    return MODALIDADES.get(modalidade, "nao_identificado")


def baixar_cadastro(cliente: ClienteANS, dir_bronze: Path) -> tuple[Path, Path]:
    # O cadastro muda diariamente: sempre baixa a versão do dia (se mudou no servidor)
    ativas = cliente.baixar(
        cliente.url(CAMINHO_CADOP_ATIVAS), dir_bronze / "cadop" / "Relatorio_cadop.csv"
    )
    canceladas = cliente.baixar(
        cliente.url(CAMINHO_CADOP_CANCELADAS),
        dir_bronze / "cadop" / "Relatorio_cadop_canceladas.csv",
    )
    return ativas, canceladas


def ler_cadop(caminho: Path, situacao: str) -> pd.DataFrame:
    bruto = ler_csv_texto(caminho)
    mapa = mapear_colunas(list(bruto.columns), ALIASES_CADOP)
    if "REG_ANS" not in mapa:
        raise ValueError(
            f"{caminho.name}: coluna de registro ANS não encontrada. Colunas: {list(bruto.columns)}"
        )

    def col(nome: str) -> pd.Series:
        return bruto[mapa[nome]].str.strip() if nome in mapa else pd.Series("", index=bruto.index)

    df = pd.DataFrame(
        {
            "reg_ans": normalizar_reg_ans(col("REG_ANS")),
            "cnpj": col("CNPJ").str.replace(r"\D", "", regex=True).str.zfill(14),
            "razao_social": col("RAZAO_SOCIAL"),
            "nome_fantasia": col("NOME_FANTASIA"),
            "modalidade_original": col("MODALIDADE"),
            "cidade": col("CIDADE"),
            "uf": col("UF").str.upper(),
            "data_registro": col("DATA_REGISTRO"),
            "data_cancelamento": col("DATA_CANCELAMENTO"),
            "motivo_cancelamento": col("MOTIVO_CANCELAMENTO"),
        }
    )
    df["situacao"] = situacao
    df = df.dropna(subset=["reg_ans"])
    df["modalidade"] = df["modalidade_original"].map(padronizar_modalidade)
    df["segmento"] = df["modalidade"].map(segmento_da_modalidade)
    df["nome"] = df["nome_fantasia"].where(
        df["nome_fantasia"].fillna("").str.len() > 0, df["razao_social"]
    )
    return df


def montar_cadastro(ativas: Path, canceladas: Path | None) -> pd.DataFrame:
    partes = [ler_cadop(Path(ativas), "ativa")]
    if canceladas and Path(canceladas).exists():
        partes.append(ler_cadop(Path(canceladas), "cancelada"))
    df = pd.concat(partes, ignore_index=True)
    # Se o registro aparece nas duas listas, vale a situação "ativa"
    df = df.drop_duplicates(subset=["reg_ans"], keep="first").reset_index(drop=True)
    nao_id = (df["modalidade"] == MODALIDADE_NAO_IDENTIFICADA).sum()
    if len(df) and nao_id / len(df) > 0.5:
        log.error(
            "A maioria das modalidades do CADOP não foi reconhecida — o layout pode ter mudado. "
            "Valores encontrados: %s. Ajuste _REGRAS_MODALIDADE em cadastro.py.",
            list(df["modalidade_original"].value_counts().head(8).index),
        )
    elif nao_id:
        exemplos = df.loc[
            df["modalidade"] == MODALIDADE_NAO_IDENTIFICADA, "modalidade_original"
        ].unique()[:5]
        log.warning(
            "%d operadoras com modalidade não reconhecida (ex.: %s)", nao_id, list(exemplos)
        )
    log.info("Cadastro: %d operadoras (%d ativas)", len(df), (df["situacao"] == "ativa").sum())
    return df
