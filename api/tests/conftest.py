"""Shared test fixtures/configuration.

Sets the required env vars before app modules import ``settings`` so
``Settings()`` can be instantiated without a real database/redis. sqlite needs
no external driver and these tests never touch the DB (``create_engine`` only
connects lazily, but eagerly imports the driver — sqlite avoids that).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
