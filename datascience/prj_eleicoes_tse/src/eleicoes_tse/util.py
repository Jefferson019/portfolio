from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
)
log = logging.getLogger("eleicoes_tse")


def salvar_tabela(df: pd.DataFrame, caminho: Path) -> Path:
    """Salva em Parquet se o pyarrow estiver instalado; senão em CSV comprimido."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow  # noqa: F401

        destino = caminho.with_suffix(".parquet")
        df.to_parquet(destino, index=False)
    except ImportError:
        destino = caminho.with_suffix(".csv.gz")
        df.to_csv(destino, index=False)
    return destino


def ler_tabela(caminho: Path) -> pd.DataFrame | None:
    for sufixo in (".parquet", ".csv.gz"):
        arquivo = caminho.with_suffix(sufixo)
        if arquivo.exists():
            return pd.read_parquet(arquivo) if sufixo == ".parquet" else pd.read_csv(arquivo)
    return None


def pct(parte, todo):
    return 100 * parte / todo
