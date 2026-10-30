"""Logs estruturados (JSON) com contexto de execução.

A recomendação oficial é emitir logs com nome do bundle, ambiente,
workload, id da execução e um identificador de negócio, e centralizar
isso numa biblioteca compartilhada — que é o papel deste módulo.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


class _JsonFormatter(logging.Formatter):
    def __init__(self, contexto: dict[str, Any]) -> None:
        super().__init__()
        self._contexto = contexto

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            **self._contexto,
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(workload: str, **contexto: Any) -> logging.Logger:
    """Cria um logger JSON. O run id vem da variável de ambiente, se houver."""
    base = {
        "bundle": "contas_medicas",
        "workload": workload,
        "run_id": os.getenv("DATABRICKS_JOB_RUN_ID", "local"),
        **contexto,
    }
    logger = logging.getLogger(f"contas_medicas.{workload}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter(base))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
