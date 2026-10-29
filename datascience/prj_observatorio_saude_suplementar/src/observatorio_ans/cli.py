"""Linha de comando: `python -m observatorio_ans [tudo|painel] [opções]`."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Config
from .util import configurar_log, log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="observatorio-ans",
        description="Baixa os dados abertos da ANS, calcula sinistralidade e indicadores de mercado e gera o painel.",
    )
    parser.add_argument(
        "comando",
        nargs="?",
        default="tudo",
        choices=["tudo", "painel"],
        help="tudo = pipeline completo (padrão); painel = só regera o site a partir de dados/ouro",
    )
    parser.add_argument(
        "--ano-inicio",
        type=int,
        help="primeiro ano das demonstrações contábeis (padrão: projeto.toml)",
    )
    parser.add_argument(
        "--ano-fim", type=int, help="último ano (padrão: o mais recente disponível)"
    )
    parser.add_argument(
        "--sem-beneficiarios",
        action="store_true",
        help="não baixa o SIB (mais rápido; usa o histórico já existente em dados/historico)",
    )
    parser.add_argument(
        "--sem-download",
        action="store_true",
        help="modo offline: usa apenas arquivos já presentes em dados/bronze",
    )
    parser.add_argument(
        "--forcar-download", action="store_true", help="baixa de novo mesmo o que já está em cache"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log detalhado")
    args = parser.parse_args(argv)

    configurar_log(logging.DEBUG if args.verbose else logging.INFO)
    cfg = Config.carregar()
    if args.ano_inicio:
        cfg.ano_inicio = args.ano_inicio
    if args.ano_fim:
        cfg.ano_fim = args.ano_fim

    from . import pipeline  # import tardio: deixa o --help rápido

    try:
        if args.comando == "painel":
            pipeline.regerar_painel(cfg)
        else:
            pipeline.executar(
                cfg,
                sem_download=args.sem_download,
                sem_beneficiarios=args.sem_beneficiarios,
                forcar_download=args.forcar_download,
            )
    except Exception as erro:  # mensagem curta para o usuário; detalhes com -v
        log.error("%s", erro)
        if args.verbose:
            raise
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
