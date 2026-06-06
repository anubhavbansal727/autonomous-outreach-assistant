"""Shared fixtures for API-layer tests.

All tests in tests/api/ use FastAPI's ASGI test transport via httpx.
External dependencies (DB, Redis, ARQ, Resend) are replaced with mocks
via dependency_overrides and unittest.mock.patch — no real services required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.main import create_app

# ---------------------------------------------------------------------------
# Stable IDs / timestamps used throughout the test suite
# ---------------------------------------------------------------------------

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PROFILE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
JOB_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
BATCH_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")
CREATED_AT = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_result(scalar=None, scalars_all=None, scalar_one=0):
    """Return a mock that mimics a SQLAlchemy AsyncResult.

    - result.scalar_one_or_none() → scalar
    - result.scalars().all()       → scalars_all
    - result.scalar_one()          → scalar_one
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalar_one.return_value = scalar_one
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = scalars_all or []
    result.scalars.return_value = scalars_mock
    return result


def make_profile(
    profile_id=None,
    product_name="Test Product",
    one_liner="The best product",
    target_customer="SMBs",
    pain_points=None,
    differentiators=None,
    case_studies=None,
    cta="Book a demo",
    icp="B2B SaaS teams",
    avoid_messaging=None,
    source_url="https://example.com",
    is_active=True,
):
    """Return a MagicMock that looks like a ProductProfile ORM row."""
    p = MagicMock()
    p.id = profile_id or PROFILE_ID
    p.product_name = product_name
    p.one_liner = one_liner
    p.target_customer = target_customer
    p.pain_points = pain_points or ["pain1", "pain2"]
    p.differentiators = differentiators or ["diff1"]
    p.case_studies = case_studies or []
    p.cta = cta
    p.icp = icp
    p.avoid_messaging = avoid_messaging
    p.source_url = source_url
    p.is_active = is_active
    p.updated_at = CREATED_AT
    return p


def make_outreach_job(
    job_id=None,
    company_name="Acme Corp",
    contact_name="Jane Doe",
    status="done",
    send_status="draft",
    current_step="complete",
    email_subject="Hello from Test Product",
    email_draft="Hi Jane, ...",
    linkedin_draft="Hi Jane on LinkedIn...",
    data_confidence="high",
    schedule_json=None,
    error_message=None,
    token_usage=1200,
    completed_at=None,
    retry_count=0,
):
    """Return a MagicMock that looks like an OutreachJob ORM row."""
    j = MagicMock()
    j.id = job_id or JOB_ID
    j.company_name = company_name
    j.contact_name = contact_name
    j.status = status
    j.send_status = send_status
    j.current_step = current_step
    j.email_subject = email_subject
    j.email_draft = email_draft
    j.linkedin_draft = linkedin_draft
    j.data_confidence = data_confidence
    j.schedule_json = schedule_json
    j.error_message = error_message
    j.token_usage = token_usage
    j.created_at = CREATED_AT
    j.completed_at = completed_at or CREATED_AT
    j.retry_count = retry_count
    return j


def make_batch_job(
    batch_id=None,
    status="running",
    total=3,
    research_done=0,
    personalize_done=0,
    completed_at=None,
):
    """Return a MagicMock that looks like a BatchJob ORM row."""
    b = MagicMock()
    b.id = batch_id or BATCH_ID
    b.status = status
    b.total = total
    b.research_done = research_done
    b.personalize_done = personalize_done
    b.created_at = CREATED_AT
    b.completed_at = completed_at
    return b


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_user():
    """MagicMock representing an authenticated User ORM row."""
    user = MagicMock()
    user.id = USER_ID
    user.email = "test@example.com"
    user.resend_domain = None
    user.created_at = CREATED_AT
    user.password_hash = "$2b$12$fakehash"  # not used in authed routes
    return user


@pytest.fixture
def mock_db():
    """AsyncMock session with sensible no-op defaults.

    configure mock_db.execute.return_value = make_result(...) per test
    to control what the DB "returns".
    """
    db = AsyncMock()
    db.commit = AsyncMock(return_value=None)
    db.flush = AsyncMock(return_value=None)
    db.add = MagicMock(return_value=None)
    db.delete = AsyncMock(return_value=None)

    async def _fake_refresh(obj):
        """Simulate SQLAlchemy server_default population after flush."""
        if not getattr(obj, "id", None):
            obj.id = JOB_ID
        if not getattr(obj, "created_at", None):
            obj.created_at = CREATED_AT
        if not getattr(obj, "updated_at", None):
            obj.updated_at = CREATED_AT

    db.refresh = AsyncMock(side_effect=_fake_refresh)
    db.execute = AsyncMock(return_value=make_result())
    return db


@pytest.fixture
def authed_app(fake_user, mock_db):
    """FastAPI app with get_current_user + get_db overridden (authenticated)."""
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_db] = lambda: mock_db
    return app


@pytest.fixture
def anon_app(mock_db):
    """FastAPI app with only get_db overridden (for auth/ endpoints)."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    return app


@pytest_asyncio.fixture
async def authed_client(authed_app):
    """Async HTTP client wired to authed_app (no real network)."""
    async with AsyncClient(
        transport=ASGITransport(app=authed_app), base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def anon_client(anon_app):
    """Async HTTP client wired to anon_app (no real network)."""
    async with AsyncClient(
        transport=ASGITransport(app=anon_app), base_url="http://test"
    ) as client:
        yield client
