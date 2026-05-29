"""Shared pytest fixtures for Mini CRM AI Crew backend tests.

Unit tests use mocks and never touch a real DB or Redis.
API tests use FastAPI's TestClient with all external dependencies overridden.
Integration tests (in tests/integration/) require a running Postgres + Redis.
"""
from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Ensure env vars are set before any app module is imported at collection time.
# These values are only used for the test session — they never reach production.
# ---------------------------------------------------------------------------

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-bytes-long!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("RESEND_API_KEY", "re_test_key")
os.environ.setdefault("SERPER_API_KEY", "serper-test-key")
