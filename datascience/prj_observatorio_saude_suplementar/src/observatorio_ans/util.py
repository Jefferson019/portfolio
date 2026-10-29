"""Funções auxiliares: texto, números no padrão brasileiro, períodos e leitura de CSV."""

from __future__ import annotations

import io
import logging
import re
import unicodedata

import numpy as np
import pandas as pd

log = logging.getLogger("observatorio_ans")


def configurar_log(nivel: int = logging.INFO) -> None:
    logging.basicConfig(
        level=nivel,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


# ----------------------------------------------------------------------------- texto


def sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_texto(texto: object) -> str:
    """Maiúsculas, sem acentos e com espaços simples. Útil para comparar descrições."""
    if texto is None or (isinstance(texto, float) and np.isnan(texto)):
        return ""
    t = sem_acento(str(texto)).upper()
    return re.sub(r"\s+", " ", t).strip()


def normalizar_coluna(nome: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", normalizar_texto(nome)).strip("_")


# ----------------------------------------------------------------------------- números


def parse_valor_br(serie: pd.Series) -> pd.Series:
    """Converte textos como '1.234.567,89', '1234567,89', '-12,5' ou '1234.5' em float."""
    s = serie.astype("string").str.strip().str.replace(" ", "", regex=False)
    s = s.str.replace(" ", "", regex=False)
    # Formato contábil: (1.234,56) significa negativo
    entre_parenteses = s.str.match(r"^\(.*\)$", na=False)
    s = s.where(~entre_parenteses, "-" + s.str.slice(1, -1))
    tem_virgula = s.str.contains(",", regex=False, na=False)
    # Com vírgula: pontos são separadores de milhar e a vírgula é decimal
    s = s.where(
        ~tem_virgula, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    )
    # Sem vírgula e com mais de um ponto: pontos são separadores de milhar
    varios_pontos = (~tem_virgula) & (s.str.count(r"\.") > 1)
    s = s.where(~varios_pontos, s.str.replace(".", "", regex=False))
    return pd.to_numeric(s, errors="coerce").astype("float64")


def normalizar_reg_ans(serie: pd.Series) -> pd.Series:
    """Registro ANS como texto de 6 dígitos (ex.: '5711' -> '005711')."""
    s = serie.astype("string").str.replace(r"\D", "", regex=True)
    s = s.where(s.str.len() > 0)
    return s.str.zfill(6)


def normalizar_conta(serie: pd.Series) -> pd.Series:
    return serie.astype("string").str.replace(r"\D", "", regex=True)


def dividir(numerador, denominador, minimo: float = 1.0):
    """Divisão segura: retorna NaN quando o denominador é <= mínimo (ou ausente)."""
    num = pd.to_numeric(numerador, errors="coerce")
    den = pd.to_numeric(denominador, errors="coerce")
    if isinstance(den, pd.Series):
        den = den.where(den > minimo)
        return (num / den).astype("float64")
    if den is None or not np.isfinite(den) or den <= minimo:
        return np.nan
    return float(num) / float(den)


# ----------------------------------------------------------------------------- períodos


def periodo(ano: int, tri: int) -> str:
    return f"{int(ano)}T{int(tri)}"


def rotulo_periodo(ano: int, tri: int) -> str:
    return f"{int(tri)}º tri/{int(ano)}"


def separar_periodo(p: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{4})T([1-4])", p)
    if not m:
        raise ValueError(f"Período inválido: {p!r} (esperado AAAATn)")
    return int(m.group(1)), int(m.group(2))


def indice_trimestre(ano: int, tri: int) -> int:
    """Número sequencial do trimestre, útil para ordenar e calcular defasagens."""
    return int(ano) * 4 + int(tri) - 1


def do_indice(indice: int) -> tuple[int, int]:
    return indice // 4, indice % 4 + 1


# ----------------------------------------------------------------------------- CSV


def detectar_encoding(amostra: bytes) -> str:
    """Retorna 'utf-8-sig' se a amostra decodifica como UTF-8; senão 'latin-1'."""
    try:
        amostra.decode("utf-8")
        return "utf-8-sig"
    except UnicodeDecodeError as erro:
        # Uma amostra cortada no meio de um caractere multibyte também falha:
        # só considera latin-1 se o erro não estiver nos últimos 3 bytes.
        if erro.start >= len(amostra) - 3:
            return "utf-8-sig"
        return "latin-1"


def detectar_separador(primeira_linha: str) -> str:
    candidatos = [";", ",", "\t", "|"]
    return max(candidatos, key=primeira_linha.count)


def inspecionar_csv(abrir, tamanho_amostra: int = 2_000_000) -> tuple[str, str, list[str]]:
    """Lê uma amostra do arquivo e devolve (encoding, separador, colunas originais).

    `abrir` é uma função sem argumentos que devolve um arquivo binário novo (ex.: um membro
    de um zip). A amostra é lida e descartada; o arquivo é reaberto depois para a leitura completa.
    """
    with abrir() as f:
        amostra = f.read(tamanho_amostra)
    encoding = detectar_encoding(amostra)
    texto = amostra.decode(encoding, errors="replace")
    primeira = texto.splitlines()[0] if texto else ""
    sep = detectar_separador(primeira)
    colunas = [c.strip().strip('"').strip() for c in primeira.split(sep)]
    return encoding, sep, colunas


def mapear_colunas(colunas: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    """Mapeia nomes canônicos -> nome original da coluna, aceitando apelidos.

    Ex.: aliases = {"REG_ANS": ["REG_ANS", "REGISTRO_ANS", "CD_OPERADORA"]}
    """
    normalizadas = {normalizar_coluna(c): c for c in colunas}
    mapa: dict[str, str] = {}
    for canonico, opcoes in aliases.items():
        for opcao in opcoes:
            if normalizar_coluna(opcao) in normalizadas:
                mapa[canonico] = normalizadas[normalizar_coluna(opcao)]
                break
    return mapa


def ler_csv_texto(fonte: bytes | str, **kwargs) -> pd.DataFrame:
    """Lê um CSV inteiro (bytes ou caminho) detectando encoding e separador."""
    if isinstance(fonte, (bytes, bytearray)):
        dados = bytes(fonte)
    else:
        with open(fonte, "rb") as f:
            dados = f.read()
    encoding, sep, _ = inspecionar_csv(lambda: io.BytesIO(dados))
    return pd.read_csv(
        io.BytesIO(dados),
        sep=sep,
        dtype=str,
        encoding=encoding,
        encoding_errors="replace",
        keep_default_na=False,
        **kwargs,
    )
