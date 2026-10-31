"""Download dos arquivos de dados abertos do TSE, com cache local e novas tentativas."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import requests

from .config import CONJUNTOS, Config
from .util import log

USER_AGENT = "prj-eleicoes-tse/0.1 (portfolio; dados abertos TSE)"


class ErroDownload(RuntimeError):
    pass


def url_arquivo(cfg: Config, conjunto: str, ano: int) -> str:
    base = cfg.url_base if cfg.url_base.endswith("/") else cfg.url_base + "/"
    return f"{base}{conjunto}/{CONJUNTOS[conjunto].format(ano=ano)}"


def baixar(cfg: Config, conjunto: str, ano: int, tentativas: int = 4) -> Path:
    """Baixa o .zip do conjunto/ano para dados/bronze; reaproveita se já existir e estiver íntegro."""
    url = url_arquivo(cfg, conjunto, ano)
    destino = cfg.bronze / conjunto / url.rsplit("/", 1)[-1]
    if destino.exists() and zipfile.is_zipfile(destino):
        log.info("Já baixado: %s", destino.name)
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".zip.part")
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            log.info("Baixando %s", url)
            with requests.get(
                url, stream=True, timeout=(30, 600), headers={"User-Agent": USER_AGENT}
            ) as resp:
                if resp.status_code == 404:
                    raise ErroDownload(f"Arquivo não encontrado no TSE (HTTP 404): {url}")
                resp.raise_for_status()
                with open(parcial, "wb") as f:
                    for bloco in resp.iter_content(chunk_size=1 << 20):
                        f.write(bloco)
            if not zipfile.is_zipfile(parcial):
                raise ErroDownload(f"O arquivo baixado de {url} não é um .zip válido")
            parcial.replace(destino)
            log.info("Salvo em %s (%.1f MB)", destino, destino.stat().st_size / 1e6)
            return destino
        except ErroDownload:
            raise
        except requests.RequestException as erro:
            ultimo_erro = erro
            espera = 2 ** (tentativa + 1)
            log.warning("Falha ao baixar %s (%s). Nova tentativa em %ss", url, erro, espera)
            time.sleep(espera)
    raise ErroDownload(f"Não foi possível baixar {url}: {ultimo_erro}")
