"""Leitura dos CSVs de dentro dos .zip do TSE e padronização das colunas.

Particularidades dos arquivos do TSE tratadas aqui:
- separador ``;``, aspas em todos os campos, codificação Latin-1 (alguns anos em UTF-8);
- um CSV por UF dentro do .zip e, em alguns conjuntos/anos, também um arquivo ``_BR``/``_BRASIL``
  (às vezes só com a eleição presidencial, às vezes com tudo). Lemos todos e removemos linhas
  repetidas pela chave natural, o que evita contar votos em dobro nos dois casos;
- nomes de colunas que mudam entre os anos (ex.: ``QT_VOTOS_NOMINAIS_VALIDOS`` só existe a partir
  de 2022). Para cada campo há uma lista de nomes aceitos, do mais novo para o mais antigo;
- valores ausentes codificados como ``#NULO#``, ``#NE#``, ``-1``, ``-3``.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from .config import CARGO_PRESIDENTE, REGIAO_DA_UF
from .util import log

NULOS_TSE = ["#NULO#", "#NULO", "#NE#", "#NE", ""]

# campo padronizado -> nomes aceitos no arquivo do TSE (o primeiro encontrado é usado)
CAMPOS_VOTACAO = {
    "ano": ["ANO_ELEICAO"],
    "cd_eleicao": ["CD_ELEICAO"],
    "turno": ["NR_TURNO"],
    "uf": ["SG_UF"],
    "cd_municipio": ["CD_MUNICIPIO"],
    "municipio": ["NM_MUNICIPIO"],
    "zona": ["NR_ZONA"],
    "cd_cargo": ["CD_CARGO"],
    "sq_candidato": ["SQ_CANDIDATO"],
    "nr_candidato": ["NR_CANDIDATO"],
    "candidato": ["NM_URNA_CANDIDATO"],
    "partido": ["SG_PARTIDO"],
    "votos": ["QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_NOMINAIS"],
}
CHAVE_VOTACAO = ["ano", "cd_eleicao", "turno", "cd_municipio", "zona", "cd_cargo", "sq_candidato"]

CAMPOS_DETALHE = {
    "ano": ["ANO_ELEICAO"],
    "cd_eleicao": ["CD_ELEICAO"],
    "turno": ["NR_TURNO"],
    "uf": ["SG_UF"],
    "cd_municipio": ["CD_MUNICIPIO"],
    "municipio": ["NM_MUNICIPIO"],
    "zona": ["NR_ZONA"],
    "cd_cargo": ["CD_CARGO"],
    "aptos": ["QT_APTOS"],
    "comparecimento": ["QT_COMPARECIMENTO"],
    "abstencoes": ["QT_ABSTENCOES"],
    "validos": ["QT_VOTOS_VALIDOS"],
    "nominais": ["QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_NOMINAIS"],
    "legenda": ["QT_VOTOS_LEGENDA_VALIDOS", "QT_VOTOS_LEGENDA"],
    "brancos": ["QT_VOTOS_BRANCOS"],
    "nulos": ["QT_TOTAL_VOTOS_NULOS", "QT_VOTOS_NULOS"],
}
CHAVE_DETALHE = ["ano", "cd_eleicao", "turno", "cd_municipio", "zona", "cd_cargo"]

CAMPOS_CANDIDATOS = {
    "ano": ["ANO_ELEICAO"],
    "turno": ["NR_TURNO"],
    "uf": ["SG_UF"],
    "cd_cargo": ["CD_CARGO"],
    "cargo": ["DS_CARGO"],
    "sq_candidato": ["SQ_CANDIDATO"],
    "candidato": ["NM_URNA_CANDIDATO"],
    "partido": ["SG_PARTIDO"],
    "genero": ["DS_GENERO"],
    "cor_raca": ["DS_COR_RACA"],
    "instrucao": ["DS_GRAU_INSTRUCAO"],
    "idade": ["NR_IDADE_DATA_POSSE"],
    "situacao_candidatura": ["DS_SITUACAO_CANDIDATURA"],
    "situacao_turno": ["DS_SIT_TOT_TURNO"],
}

NUMERICOS = {
    "ano", "cd_eleicao", "turno", "cd_municipio", "zona", "cd_cargo", "sq_candidato",
    "nr_candidato", "votos", "aptos", "comparecimento", "abstencoes", "validos", "nominais",
    "legenda", "brancos", "nulos", "idade",
}  # fmt: skip


def _codificacao(amostra: bytes) -> str:
    try:
        amostra.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _mapear_colunas(cabecalho: list[str], campos: dict[str, list[str]]) -> dict[str, str]:
    """Devolve {coluna_no_arquivo: campo_padronizado} para os campos encontrados."""
    mapa = {}
    for campo, nomes in campos.items():
        for nome in nomes:
            if nome in cabecalho:
                mapa[nome] = campo
                break
    return mapa


def ler_zip(
    caminho: Path,
    campos: dict[str, list[str]],
    filtro: Callable[[pd.DataFrame], pd.Series] | None = None,
    obrigatorios: tuple[str, ...] = (),
    tamanho_bloco: int = 500_000,
) -> pd.DataFrame:
    """Lê todos os CSVs do .zip, só com as colunas pedidas, aplicando o filtro bloco a bloco."""
    partes = []
    with zipfile.ZipFile(caminho) as zf:
        membros = [m for m in zf.namelist() if m.lower().endswith((".csv", ".txt"))]
        if not membros:
            raise ValueError(f"Nenhum CSV dentro de {caminho.name}")
        for membro in membros:
            with zf.open(membro) as bruto:
                amostra = bruto.read(1 << 16)
            cod = _codificacao(amostra)
            cabecalho = amostra.decode(cod, errors="replace").splitlines()[0]
            cabecalho = [c.strip().strip('"') for c in cabecalho.split(";")]
            mapa = _mapear_colunas(cabecalho, campos)
            faltando = [c for c in obrigatorios if c not in mapa.values()]
            if faltando:
                log.warning(
                    "%s/%s sem as colunas %s; arquivo ignorado", caminho.name, membro, faltando
                )
                continue
            with zf.open(membro) as bruto:
                texto = io.TextIOWrapper(bruto, encoding=cod, errors="replace", newline="")
                leitor = pd.read_csv(
                    texto,
                    sep=";",
                    dtype=str,
                    usecols=list(mapa),
                    na_values=NULOS_TSE,
                    keep_default_na=False,
                    chunksize=tamanho_bloco,
                )
                for bloco in leitor:
                    bloco = bloco.rename(columns=mapa)
                    for col in NUMERICOS & set(bloco.columns):
                        bloco[col] = pd.to_numeric(bloco[col], errors="coerce")
                    if filtro is not None:
                        bloco = bloco[filtro(bloco)]
                    if len(bloco):
                        partes.append(bloco)
            log.info("  lido %s", membro)
    if not partes:
        return pd.DataFrame(columns=list(campos))
    df = pd.concat(partes, ignore_index=True)
    for campo in campos:
        if campo not in df.columns:
            df[campo] = pd.NA
    return df[list(campos)]


def _deduplicar(df: pd.DataFrame, chave: list[str], nome: str) -> pd.DataFrame:
    antes = len(df)
    df = df.drop_duplicates(subset=chave, keep="first")
    if antes != len(df):
        log.info("  %s: %d linhas repetidas entre arquivos UF/BR removidas", nome, antes - len(df))
    return df


def _somente_presidente(df: pd.DataFrame) -> pd.Series:
    return df["cd_cargo"] == CARGO_PRESIDENTE


def votacao_presidente(caminho: Path) -> pd.DataFrame:
    """Votos nominais de cada candidato a presidente por município e zona."""
    df = ler_zip(caminho, CAMPOS_VOTACAO, _somente_presidente, obrigatorios=("cd_cargo", "votos"))
    df = _deduplicar(df, CHAVE_VOTACAO, "votação")
    df["votos"] = df["votos"].fillna(0).astype("int64")
    df["regiao"] = df["uf"].map(REGIAO_DA_UF)
    return df.reset_index(drop=True)


def detalhe_presidente(caminho: Path) -> pd.DataFrame:
    """Aptos, comparecimento, abstenções, válidos, brancos e nulos da eleição presidencial."""
    df = ler_zip(caminho, CAMPOS_DETALHE, _somente_presidente, obrigatorios=("cd_cargo", "aptos"))
    df = _deduplicar(df, CHAVE_DETALHE, "detalhe")
    # Anos sem QT_VOTOS_VALIDOS: válidos = nominais + legenda (para presidente, legenda é zero)
    sem_validos = df["validos"].isna()
    df.loc[sem_validos, "validos"] = df.loc[sem_validos, "nominais"].fillna(0) + df.loc[
        sem_validos, "legenda"
    ].fillna(0)
    numericas = ["aptos", "comparecimento", "abstencoes", "validos", "brancos", "nulos"]
    df[numericas] = df[numericas].fillna(0).astype("int64")
    df["regiao"] = df["uf"].map(REGIAO_DA_UF)
    return df.drop(columns=["nominais", "legenda"]).reset_index(drop=True)


ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "ELEITO POR MEDIA"}


def candidaturas(caminho: Path) -> pd.DataFrame:
    """Uma linha por candidatura (último turno disputado), com perfil e se foi eleita."""
    df = ler_zip(caminho, CAMPOS_CANDIDATOS, obrigatorios=("sq_candidato", "genero"))
    df = df.sort_values("turno").drop_duplicates(subset=["sq_candidato"], keep="last")
    situacao = df["situacao_candidatura"].fillna("APTO").str.upper()
    df["apta"] = situacao.str.startswith("APTO")
    df["eleito"] = df["situacao_turno"].fillna("").str.upper().isin(ELEITO)
    df.loc[df["idade"] < 0, "idade"] = pd.NA
    df["cargo"] = df["cargo"].str.strip().str.upper()
    return df.reset_index(drop=True)
