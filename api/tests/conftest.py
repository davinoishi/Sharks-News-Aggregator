"""Shared test fixtures/configuration.

Sets the required env vars before ``app`` is imported so ``Settings()`` can be
instantiated without a real database. ``create_engine`` is lazy, so no
connection is opened at import time.
"""
import os

# sqlite needs no external driver; these tests never touch the DB, they only
# need create_engine() to succeed at import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
