"""Fixtures: espelho sintético do portal da ANS servido por HTTP local + execução do pipeline."""

from __future__ import annotations

import functools
import http.server
import os
import socketserver
import sys
import threading
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from sintetico import gerar_espelho  # noqa: E402


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # pragma: no cover
        pass


@pytest.fixture(scope="session")
def espelho(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("espelho_ans")
    gabarito = gerar_espelho(raiz, n_operadoras=40)
    handler = functools.partial(_Silencioso, directory=str(raiz))
    servidor = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    servidor.daemon_threads = True
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{servidor.server_address[1]}/"
    yield {"raiz": raiz, "url": url, "gabarito": gabarito}
    servidor.shutdown()


@pytest.fixture(scope="session")
def execucao(espelho, tmp_path_factory):
    """Roda o pipeline completo contra o espelho e devolve as saídas carregadas."""
    trabalho = tmp_path_factory.mktemp("execucao")
    variaveis = {
        "ANS_BASE_URL": espelho["url"],
        "OBS_DIR_DADOS": str(trabalho / "dados"),
        "OBS_DIR_SITE": str(trabalho / "site"),
        "OBS_ANO_INICIO": "2023",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }
    antigas = {k: os.environ.get(k) for k in variaveis}
    os.environ.update(variaveis)
    try:
        from observatorio_ans.cli import main

        codigo = main(["tudo"])
        assert codigo == 0
        dados = trabalho / "dados"
        yield {
            "dir": trabalho,
            "ops": pd.read_csv(
                dados / "ouro" / "operadoras_indicadores.csv.gz", dtype={"reg_ans": str}
            ),
            "mercado": pd.read_csv(
                dados / "ouro" / "mercado_indicadores.csv.gz", dtype={"valor": str}
            ),
            "conciliacao": pd.read_csv(dados / "ouro" / "conciliacao_ans.csv"),
            "qualidade_path": dados / "ouro" / "relatorio_qualidade.json",
            "site": trabalho / "site",
            "historico": dados / "historico",
        }
    finally:
        for k, v in antigas.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
