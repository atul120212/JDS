"""File + console logging."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from jd_collector.config import get_settings

_configured = False


def setup_logging(level: str | None = None) -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.log_dir / "jd_collector.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        pass  # In serverless/read-only environments (e.g. Vercel), console logging is sufficient

    # Keep third-party noise down.
    for noisy in ("urllib3", "apscheduler.executors", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True
