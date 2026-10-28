"""Alerts for scrape failures and data anomalies."""

from __future__ import annotations

import logging

import requests

from jd_collector.config import get_settings

log = logging.getLogger("jd_collector.alerts")


def send_alert(message: str) -> None:
    """Log the alert and, if configured, POST it to a Slack-compatible webhook."""
    log.error("ALERT: %s", message)
    url = get_settings().alert_webhook_url
    if not url:
        return
    try:
        requests.post(url, json={"text": f"[JD Collector] {message}"}, timeout=10)
    except requests.RequestException as exc:
        log.warning("Could not deliver alert to webhook: %s", exc)
