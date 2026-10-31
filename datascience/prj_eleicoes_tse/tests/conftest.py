import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
import sintetico


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def espelho_tse(tmp_path_factory):
    """Servidor HTTP local que imita o CDN do TSE com arquivos sintéticos."""
    raiz = tmp_path_factory.mktemp("cdn_tse")
    sintetico.gerar(raiz)
    servidor = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(_Silencioso, directory=str(raiz))
    )
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_port}/"
    servidor.shutdown()
