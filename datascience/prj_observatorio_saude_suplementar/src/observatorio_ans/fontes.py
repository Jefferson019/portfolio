"""Acesso ao Portal de Dados Abertos da ANS: listagem de diretórios e downloads com cache."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests

from .util import log

USER_AGENT = "observatorio-saude-suplementar/0.1 (+https://github.com; dados abertos ANS)"
_HREF = re.compile(r'href\s*=\s*"([^"]+)"', re.IGNORECASE)


@dataclass(frozen=True)
class Entrada:
    nome: str
    url: str
    diretorio: bool


class ErroFonte(RuntimeError):
    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.status = status


class ClienteANS:
    """Cliente HTTP simples para o servidor de arquivos da ANS (índices no estilo Apache)."""

    def __init__(self, url_base: str, permitir_http: bool = False, tentativas: int = 4):
        self.url_base = url_base if url_base.endswith("/") else url_base + "/"
        self.permitir_http = permitir_http
        self.tentativas = tentativas
        self.sessao = requests.Session()
        self.sessao.headers["User-Agent"] = USER_AGENT

    # ------------------------------------------------------------------ HTTP básico

    def url(self, caminho: str) -> str:
        return urljoin(self.url_base, caminho)

    def _requisitar(self, metodo: str, url: str, **kwargs) -> requests.Response:
        ultimo_erro: Exception | None = None
        for tentativa in range(1, self.tentativas + 1):
            try:
                resp = self.sessao.request(metodo, url, timeout=(20, 300), **kwargs)
                codigo = resp.status_code
                if 400 <= codigo < 500 and codigo != 429:
                    # Erros do cliente (404, 403, 405...) não melhoram com nova tentativa
                    raise ErroFonte(f"HTTP {codigo} ao acessar {url}", status=codigo)
                resp.raise_for_status()
                return resp
            except requests.exceptions.SSLError as erro:
                ultimo_erro = erro
                if self.permitir_http and url.startswith("https://"):
                    url_http = "http://" + url[len("https://") :]
                    log.warning(
                        "Falha de certificado em %s; tentando via HTTP (ANS_PERMITIR_HTTP=1)", url
                    )
                    url = url_http
                    continue
                raise ErroFonte(
                    f"Erro de certificado SSL ao acessar {url}. Se o problema for do servidor da ANS, "
                    "defina ANS_PERMITIR_HTTP=1 para permitir o download via HTTP (dados públicos)."
                ) from erro
            except ErroFonte:
                raise
            except requests.RequestException as erro:
                ultimo_erro = erro
                espera = min(60, 2**tentativa)
                log.warning("Erro ao acessar %s (%s). Nova tentativa em %ss", url, erro, espera)
                time.sleep(espera)
        raise ErroFonte(f"Falha ao acessar {url}: {ultimo_erro}")

    # ------------------------------------------------------------------ listagem

    def listar(self, caminho_ou_url: str) -> list[Entrada]:
        """Lista um índice de diretório (HTML) e devolve arquivos e subpastas."""
        url = caminho_ou_url if "://" in caminho_ou_url else self.url(caminho_ou_url)
        if not url.endswith("/"):
            url += "/"
        html = self._requisitar("GET", url).text
        entradas: dict[str, Entrada] = {}
        for href in _HREF.findall(html):
            if href.startswith(("?", "#", "mailto:", "javascript:")):
                continue
            absoluta = urljoin(url, href)
            # Ignora links que não estão "abaixo" do diretório listado (ex.: Parent Directory)
            if not absoluta.startswith(url) or absoluta == url:
                continue
            relativo = absoluta[len(url) :]
            if "/" in relativo.rstrip("/"):
                continue
            nome = unquote(relativo.rstrip("/"))
            entradas[nome] = Entrada(nome=nome, url=absoluta, diretorio=relativo.endswith("/"))
        return sorted(entradas.values(), key=lambda e: e.nome)

    # ------------------------------------------------------------------ download

    def baixar(self, url: str, destino: Path, forcar: bool = False) -> Path:
        """Baixa `url` para `destino`, reaproveitando o arquivo local se não mudou no servidor.

        Guarda um arquivo lateral `.meta.json` com Last-Modified e Content-Length; antes de baixar
        de novo, faz um HEAD e compara.
        """
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        meta_path = destino.with_name(destino.name + ".meta.json")

        remoto = {}
        try:
            head = self._requisitar("HEAD", url, allow_redirects=True)
            remoto = {
                "last_modified": head.headers.get("Last-Modified"),
                "content_length": head.headers.get("Content-Length"),
            }
        except ErroFonte as erro:
            if erro.status == 404:
                raise
            log.debug("HEAD indisponível para %s (%s); seguindo com GET", url, erro)

        if destino.exists() and destino.stat().st_size > 0 and not forcar and meta_path.exists():
            local = json.loads(meta_path.read_text())
            if (
                remoto
                and local.get("last_modified") == remoto.get("last_modified")
                and str(local.get("content_length")) == str(remoto.get("content_length"))
            ):
                log.debug("Em cache: %s", destino.name)
                return destino

        log.info("Baixando %s", url)
        temporario = destino.with_name(destino.name + ".parcial")
        resp = self._requisitar("GET", url, stream=True)
        total = 0
        with open(temporario, "wb") as f:
            for bloco in resp.iter_content(chunk_size=1 << 20):
                f.write(bloco)
                total += len(bloco)
        esperado = resp.headers.get("Content-Length")
        if esperado and int(esperado) != total:
            temporario.unlink(missing_ok=True)
            raise ErroFonte(f"Download incompleto de {url}: {total} de {esperado} bytes")
        temporario.replace(destino)
        meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "last_modified": remoto.get("last_modified")
                    or resp.headers.get("Last-Modified"),
                    "content_length": remoto.get("content_length") or esperado or total,
                    "baixado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
        )
        return destino


def nome_arquivo(url: str) -> str:
    return unquote(Path(urlparse(url).path).name)
