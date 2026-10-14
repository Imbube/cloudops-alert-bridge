"""Logs estruturados: cada linha é um JSON (fácil de buscar em ferramentas de log)."""
import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Campos extras passados via logger.info(..., extra={"fields": {...}})
        data.update(getattr(record, "fields", {}))
        return json.dumps(data, ensure_ascii=False, default=str)


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("alert_bridge")
    if not logger.handlers:  # evita duplicar handlers
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = True
    return logger
