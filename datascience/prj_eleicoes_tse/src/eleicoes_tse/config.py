"""Endereços do TSE, anos analisados e pastas de trabalho."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Repositório de dados abertos do TSE (o mesmo que o Portal de Dados Abertos aponta)
URL_BASE_TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele/"

# Conjuntos usados: pasta no CDN -> prefixo do arquivo .zip
CONJUNTOS = {
    "votacao_candidato_munzona": "votacao_candidato_munzona_{ano}.zip",
    "detalhe_votacao_munzona": "detalhe_votacao_munzona_{ano}.zip",
    "consulta_cand": "consulta_cand_{ano}.zip",
}

ANOS_PADRAO = (2018, 2022)
CARGO_PRESIDENTE = 1

REGIOES = {
    "Norte": ["AC", "AM", "AP", "PA", "RO", "RR", "TO"],
    "Nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Centro-Oeste": ["DF", "GO", "MS", "MT"],
    "Sudeste": ["ES", "MG", "RJ", "SP"],
    "Sul": ["PR", "RS", "SC"],
}
REGIAO_DA_UF = {uf: regiao for regiao, ufs in REGIOES.items() for uf in ufs}
REGIAO_DA_UF["ZZ"] = "Exterior"


@dataclass
class Config:
    raiz: Path = field(default_factory=lambda: Path.cwd())
    anos: tuple[int, ...] = ANOS_PADRAO
    url_base: str = field(default_factory=lambda: os.environ.get("TSE_URL_BASE", URL_BASE_TSE))

    @property
    def bronze(self) -> Path:
        """Arquivos .zip originais, exatamente como baixados do TSE."""
        return self.raiz / "dados" / "bronze"

    @property
    def prata(self) -> Path:
        """Tabelas extraídas e padronizadas (Parquet ou CSV), uma por conjunto e ano."""
        return self.raiz / "dados" / "prata"

    @property
    def resultados(self) -> Path:
        """Tabelas finais da análise (versionadas no Git)."""
        return self.raiz / "dados" / "resultados"

    @property
    def relatorio(self) -> Path:
        return self.raiz / "relatorio"
