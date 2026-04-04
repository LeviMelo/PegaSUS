from __future__ import annotations

import logging


_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format=_LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
