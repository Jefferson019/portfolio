"""Configuração: caminhos, URLs da ANS, modalidades e parâmetros do pipeline."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

URL_BASE_PADRAO = "https://dadosabertos.ans.gov.br/FTP/PDA/"

# Caminhos relativos à URL base do Portal de Dados Abertos da ANS
CAMINHO_CONTABIL = "demonstracoes_contabeis/"
CAMINHO_CADOP_ATIVAS = "operadoras_de_plano_de_saude_ativas/Relatorio_cadop.csv"
CAMINHO_CADOP_CANCELADAS = "operadoras_de_plano_de_saude_canceladas/Relatorio_cadop_canceladas.csv"
# O nome da pasta de beneficiários já mudou (ganhou o sufixo "-024"); por isso é descoberto
# listando a raiz e procurando este prefixo.
PREFIXO_BENEFICIARIOS = "informacoes_consolidadas_de_beneficiarios"

# Modalidades oficiais (nome canônico) e o segmento ao qual pertencem
MODALIDADES = {
    "Autogestão": "medico_hospitalar",
    "Cooperativa Médica": "medico_hospitalar",
    "Filantropia": "medico_hospitalar",
    "Medicina de Grupo": "medico_hospitalar",
    "Seguradora Especializada em Saúde": "medico_hospitalar",
    "Cooperativa Odontológica": "odontologico",
    "Odontologia de Grupo": "odontologico",
    "Administradora de Benefícios": "administradora",
}
MODALIDADE_NAO_IDENTIFICADA = "Não identificada"

SEGMENTOS = {
    "medico_hospitalar": "Médico-hospitalar",
    "odontologico": "Exclusivamente odontológico",
    "administradora": "Administradora de benefícios",
    "nao_identificado": "Não identificado",
}

# Porte da operadora pelo número de beneficiários (critério usado pela ANS)
LIMITE_PEQUENO_PORTE = 20_000
LIMITE_GRANDE_PORTE = 100_000

JANELAS = {
    "acumulado_ano": "Acumulado no ano",
    "trimestre": "Trimestre isolado",
    "12_meses": "Últimos 12 meses",
}


def _procurar_projeto_toml(inicio: Path) -> Path | None:
    for pasta in [inicio, *inicio.parents]:
        candidato = pasta / "projeto.toml"
        if candidato.exists():
            return candidato
    return None


@dataclass
class Config:
    """Parâmetros de execução. Valores vêm de projeto.toml e de variáveis de ambiente."""

    url_base: str = URL_BASE_PADRAO
    dir_dados: Path = Path("dados")
    dir_site: Path = Path("site")
    ano_inicio: int = 2018
    ano_fim: int | None = None
    beneficiarios_trimestres: int = 5
    sinistralidade: str = "auto"
    trimestres_no_painel: int = 24
    permitir_http: bool = False
    autor: dict = field(default_factory=dict)
    painel: dict = field(default_factory=dict)

    @property
    def dir_bronze(self) -> Path:
        return self.dir_dados / "bronze"

    @property
    def dir_prata(self) -> Path:
        return self.dir_dados / "prata"

    @property
    def dir_ouro(self) -> Path:
        return self.dir_dados / "ouro"

    @property
    def dir_historico(self) -> Path:
        """Pequenos agregados versionados no repositório (crescem a cada execução)."""
        return self.dir_dados / "historico"

    @classmethod
    def carregar(cls, raiz: Path | None = None) -> Config:
        raiz = raiz or Path.cwd()
        arquivo = _procurar_projeto_toml(raiz)
        conteudo: dict = {}
        if arquivo:
            with open(arquivo, "rb") as f:
                conteudo = tomllib.load(f)
        pipeline = conteudo.get("pipeline", {})
        painel = conteudo.get("painel", {})
        env = os.environ

        cfg = cls(
            url_base=env.get("ANS_BASE_URL", URL_BASE_PADRAO),
            dir_dados=Path(env.get("OBS_DIR_DADOS", "dados")),
            dir_site=Path(env.get("OBS_DIR_SITE", "site")),
            ano_inicio=int(env.get("OBS_ANO_INICIO", pipeline.get("ano_inicio", 2018))),
            ano_fim=int(env["OBS_ANO_FIM"]) if env.get("OBS_ANO_FIM") else None,
            beneficiarios_trimestres=int(
                env.get("OBS_BENEFICIARIOS_TRIMESTRES", pipeline.get("beneficiarios_trimestres", 5))
            ),
            sinistralidade=env.get("OBS_SINISTRALIDADE", pipeline.get("sinistralidade", "auto")),
            trimestres_no_painel=int(painel.get("trimestres_no_painel", 24)),
            permitir_http=env.get("ANS_PERMITIR_HTTP", "0") == "1",
            autor=conteudo.get("autor", {}),
            painel=painel,
        )
        if not cfg.url_base.endswith("/"):
            cfg.url_base += "/"
        if cfg.sinistralidade not in {"auto", "bruta", "liquida"}:
            raise ValueError("sinistralidade deve ser 'auto', 'bruta' ou 'liquida'")
        return cfg
