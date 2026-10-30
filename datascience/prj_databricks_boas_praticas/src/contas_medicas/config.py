"""Configuração por ambiente — sem nada hardcoded.

Os valores chegam como parâmetros de job (`--catalog`, `--schema`) ou
como configuração do pipeline (`spark.conf`). Este módulo só valida e
monta nomes totalmente qualificados do Unity Catalog.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

_IDENTIFICADOR_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Ambiente:
    """Catálogo + schema de destino de uma execução."""

    catalog: str
    schema: str

    def __post_init__(self) -> None:
        for nome, valor in (("catalog", self.catalog), ("schema", self.schema)):
            if not _IDENTIFICADOR_VALIDO.match(valor):
                raise ValueError(f"{nome} inválido para o Unity Catalog: {valor!r}")

    def tabela(self, nome: str) -> str:
        """Nome de três partes: catalog.schema.tabela (sempre qualificado)."""
        if not _IDENTIFICADOR_VALIDO.match(nome):
            raise ValueError(f"nome de tabela inválido: {nome!r}")
        return f"{self.catalog}.{self.schema}.{nome}"

    @property
    def is_prod(self) -> bool:
        return self.catalog == "prod"


def parse_args(argv: list[str] | None = None) -> Ambiente:
    """Lê `--catalog` e `--schema` (named_parameters do python_wheel_task)."""
    parser = argparse.ArgumentParser(description="Parâmetros do job contas_medicas")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    args = parser.parse_args(argv)
    return Ambiente(catalog=args.catalog, schema=args.schema)
