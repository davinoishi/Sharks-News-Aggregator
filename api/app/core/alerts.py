"""Generic outbound operational alerting (R2-F2).

A thin wrapper over the ``ALERT_WEBHOOK_URL`` webhook used by the brief-09
pipeline-health monitor, for code paths that need to raise an alert without that
monitor's health-check payload shape (e.g. the roster sync aborting on a suspect
CapWages parse). The message is always logged at ERROR; it is additionally
POSTed when a webhook is configured.
"""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_alert(message: str, **fields) -> bool:
    """Log ``message`` at ERROR and best-effort POST it to ALERT_WEBHOOK_URL.

    The body carries both ``text`` (Slack) and ``content`` (Discord) keys plus
    any extra ``fields``, matching the monitor's receiver compatibility. Returns
    True if a request was sent and accepted; network/HTTP errors are swallowed so
    alerting can never crash the caller.
    """
    logger.error("ALERT: %s", message)
    url = settings.alert_webhook_url
    if not url:
        return False

    payload = {"text": message, "content": message, **fields}
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        return True
    except Exception as exc:  # network/HTTP errors must not crash the caller
        logger.error("Failed to POST alert to webhook: %s", exc)
        return False
