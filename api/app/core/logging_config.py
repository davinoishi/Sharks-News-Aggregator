"""Central logging configuration (brief 09, C4).

The Celery tasks historically used ``print()`` for diagnostics: no levels, no
timestamps, and nothing an operator could filter on. This module gives the whole
app a single, consistent logging setup that:

- writes timestamped, level-tagged lines with the module name for task context,
- honours a ``LOG_LEVEL`` environment variable (default ``INFO``), and
- is safe to call from both the FastAPI process and the Celery worker/beat.

Use ``logging.getLogger(__name__)`` in each module and call
:func:`configure_logging` once at process start (done for you in
``app.tasks.celery_app`` and ``app.main``).
"""
import logging
import os

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S%z"

_configured = False


def configure_logging() -> None:
    """Configure the root logger from the ``LOG_LEVEL`` env var (idempotent).

    Defaults to ``INFO``. An unrecognised value also falls back to ``INFO`` so a
    typo in the environment never silences logging entirely.
    """
    global _configured
    if _configured:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = logging.getLevelName(level_name)
    if not isinstance(level, int):
        level = logging.INFO

    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=DATE_FORMAT)
    logging.getLogger().setLevel(level)
    _configured = True
