from __future__ import annotations

import argparse
from pathlib import Path

from .config import ANOS_PADRAO, Config
from .pipeline import executar


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="eleicoes-tse",
        description="Baixa os dados abertos do TSE e analisa as eleições gerais (presidente e candidaturas).",
    )
    p.add_argument(
        "--anos",
        type=int,
        nargs="+",
        default=list(ANOS_PADRAO),
        help="anos de eleição geral (ex.: 2018 2022)",
    )
    p.add_argument(
        "--raiz",
        type=Path,
        default=Path.cwd(),
        help="pasta do projeto (onde ficam dados/ e relatorio/)",
    )
    p.add_argument(
        "--refazer",
        action="store_true",
        help="reextrai as tabelas mesmo se já existirem em dados/prata",
    )
    a = p.parse_args(argv)
    for ano in a.anos:
        if ano < 2014 or (ano - 2014) % 4:
            p.error(f"{ano} não é ano de eleição geral suportado (2014, 2018, 2022, 2026...)")
    resumo = executar(Config(raiz=a.raiz, anos=tuple(sorted(a.anos))), refazer=a.refazer)
    return 0 if resumo["conferencia_ok"] is not False else 1
