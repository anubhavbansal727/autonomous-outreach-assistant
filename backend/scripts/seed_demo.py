"""Seed the database with a demo user and 5 completed outreach jobs.

Run from backend/:
    python scripts/seed_demo.py

Idempotent — safe to run multiple times. If the demo user already exists the
script updates their profile and replaces the 5 seed jobs.

Demo credentials
----------------
    email:    demo@datapulse.io
    password: Demo1234!
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

# Make sure `backend/` is on sys.path so `app.*` imports resolve when the
# script is run from the backend/ directory via `python scripts/seed_demo.py`.
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from passlib.context import CryptContext
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, engine
from app.models.db import Base, IngestionJob, OutreachJob, ProductProfile, User

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEMO_EMAIL = "demo@datapulse.io"
DEMO_PASSWORD = "Demo1234!"

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures"

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash(password: str) -> str:
    return _pwd_ctx.hash(password)


def _load_json(name: str) -> dict | list:
    return json.loads((FIXTURES_DIR / name).read_text())


def _utc_days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


# ---------------------------------------------------------------------------
# Seed steps
# ---------------------------------------------------------------------------


async def _upsert_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.email == DEMO_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=DEMO_EMAIL,
            password_hash=_hash(DEMO_PASSWORD),
            resend_domain="datapulse.io",
        )
        db.add(user)
        await db.flush()
        print(f"  Created user: {DEMO_EMAIL}")
    else:
        user.resend_domain = "datapulse.io"
        print(f"  Found existing user: {DEMO_EMAIL}")
    return user


async def _upsert_profile(db: AsyncSession, user: User) -> ProductProfile:
    # Deactivate any existing active profiles for this user.
    await db.execute(
        update(ProductProfile)
        .where(ProductProfile.user_id == user.id, ProductProfile.is_active == True)  # noqa: E712
        .values(is_active=False)
    )

    profile_data: dict = _load_json("product_profile.json")  # type: ignore[assignment]

    profile = ProductProfile(
        user_id=user.id,
        source_url="https://datapulse.io",
        product_name=profile_data["product_name"],
        one_liner=profile_data.get("one_liner"),
        target_customer=profile_data.get("target_customer"),
        pain_points=profile_data.get("pain_points", []),
        differentiators=profile_data.get("differentiators", []),
        case_studies=profile_data.get("case_studies", []),
        cta=profile_data.get("cta"),
        icp=profile_data.get("icp"),
        is_active=True,
    )
    db.add(profile)
    await db.flush()
    print(f"  Created product profile: {profile.product_name}")
    return profile


async def _seed_outreach_jobs(
    db: AsyncSession, user: User, profile: ProductProfile
) -> None:
    # Remove previous seed jobs for this user so we start fresh.
    await db.execute(delete(OutreachJob).where(OutreachJob.user_id == user.id))

    seed_jobs: list[dict] = _load_json("seed_jobs.json")  # type: ignore[assignment]

    for entry in seed_jobs:
        days_ago: int = entry.get("days_ago", 0)
        created = _utc_days_ago(days_ago)
        completed: datetime | None = None
        sent_at: datetime | None = None

        if entry["status"] == "done":
            completed = created + timedelta(minutes=2)

        if entry.get("resend_message_id"):
            sent_at = completed + timedelta(minutes=5) if completed else None

        job = OutreachJob(
            user_id=user.id,
            product_profile_id=profile.id,
            company_name=entry["company_name"],
            contact_name=entry.get("contact_name"),
            status=entry["status"],
            current_step="complete" if entry["status"] == "done" else None,
            send_status=entry["send_status"],
            data_confidence=entry.get("data_confidence"),
            email_subject=entry.get("email_subject"),
            email_draft=entry.get("email_draft"),
            linkedin_draft=entry.get("linkedin_draft"),
            schedule_json=entry.get("schedule_json"),
            resend_message_id=entry.get("resend_message_id"),
            error_message=entry.get("error_message"),
            sent_at=sent_at,
            completed_at=completed,
            created_at=created,
        )
        db.add(job)
        print(
            f"  Job: {entry['company_name']:20s} "
            f"status={entry['status']:6s}  send_status={entry['send_status']}"
        )

    await db.flush()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    print("=== Mini CRM AI Crew — Demo Seeder ===\n")

    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await _upsert_user(db)
            profile = await _upsert_profile(db, user)
            await _seed_outreach_jobs(db, user, profile)

    print("\nDone. Demo credentials:")
    print(f"  Email:    {DEMO_EMAIL}")
    print(f"  Password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
