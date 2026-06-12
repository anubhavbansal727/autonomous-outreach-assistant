"""SQLAlchemy async ORM models for Mini CRM AI Crew.

In plain English (read this first):
- This file defines the database TABLES as Python classes. One class = one
  table; one attribute = one column.
- The five tables: ``User`` (login accounts), ``ProductProfile`` (what the
  user is selling), ``IngestionJob`` (a website-scrape-to-profile run),
  ``OutreachJob`` (one generated email/LinkedIn draft — the central record),
  and ``BatchJob`` (a parent row for a CSV of many prospects).
- ``CheckConstraint``s make the database itself reject invalid values (e.g. a
  status that isn't 'running'/'done'/'failed'). The rules live in the DB, not
  just in Python.
- ``relationship(...)`` lines let you hop from one row to related rows in
  Python (e.g. a user's jobs); they don't create columns.

All tables:
- Use UUID primary keys with server_default=gen_random_uuid()
- Use TIMESTAMPTZ for all datetime columns
- Use JSONB for structured JSON blobs
- Use ARRAY(TEXT) for list-of-string columns

Relationships are declared for ORM convenience but are not loaded eagerly
by default — use selectinload() or joinedload() in queries as needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    TEXT,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(TEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(TEXT, nullable=False)
    resend_domain: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )

    # Relationships
    profiles: Mapped[list[ProductProfile]] = relationship(
        "ProductProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    ingestion_jobs: Mapped[list[IngestionJob]] = relationship(
        "IngestionJob",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    outreach_jobs: Mapped[list[OutreachJob]] = relationship(
        "OutreachJob",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    batch_jobs: Mapped[list[BatchJob]] = relationship(
        "BatchJob",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )


# ---------------------------------------------------------------------------
# ProductProfile
# ---------------------------------------------------------------------------


class ProductProfile(Base):
    __tablename__ = "product_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    product_name: Mapped[str] = mapped_column(TEXT, nullable=False)
    one_liner: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    target_customer: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    pain_points: Mapped[list[str]] = mapped_column(
        ARRAY(TEXT), server_default=text("'{}'"), nullable=False
    )
    differentiators: Mapped[list[str]] = mapped_column(
        ARRAY(TEXT), server_default=text("'{}'"), nullable=False
    )
    case_studies: Mapped[list[str]] = mapped_column(
        ARRAY(TEXT), server_default=text("'{}'"), nullable=False
    )
    cta: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    icp: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    avoid_messaging: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )

    __table_args__ = (
        # FK declared inline via ForeignKey is not used here so that the
        # constraint can be expressed alongside the table args block cleanly.
        # We use the SQLAlchemy ForeignKeyConstraint approach instead.
        Index("ix_product_profiles_user_id", "user_id"),
        # Partial unique index: only one active profile per user at a time.
        Index(
            "uq_product_profiles_user_id_active",
            "user_id",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="profiles", lazy="noload")
    outreach_jobs: Mapped[list[OutreachJob]] = relationship(
        "OutreachJob",
        back_populates="product_profile",
        lazy="noload",
    )


# ---------------------------------------------------------------------------
# IngestionJob
# ---------------------------------------------------------------------------


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(TEXT, nullable=False)
    status: Mapped[str] = mapped_column(
        TEXT,
        server_default=text("'running'"),
        nullable=False,
    )
    current_step: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ck_ingestion_jobs_status",
        ),
        CheckConstraint(
            "current_step IS NULL OR current_step IN ('scraping', 'extracting', 'complete')",
            name="ck_ingestion_jobs_current_step",
        ),
        Index("ix_ingestion_jobs_user_id", "user_id"),
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User", back_populates="ingestion_jobs", lazy="noload"
    )


# ---------------------------------------------------------------------------
# OutreachJob
# ---------------------------------------------------------------------------


class OutreachJob(Base):
    __tablename__ = "outreach_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    # When set, this job is part of a batch run. NULL for single-prospect jobs.
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batch_jobs.id", ondelete="CASCADE"),
        nullable=True,
    )
    batch_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_name: Mapped[str] = mapped_column(TEXT, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    status: Mapped[str] = mapped_column(
        TEXT,
        server_default=text("'running'"),
        nullable=False,
    )
    current_step: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    send_status: Mapped[str] = mapped_column(
        TEXT,
        server_default=text("'draft'"),
        nullable=False,
    )
    data_confidence: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    email_subject: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    email_draft: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    linkedin_draft: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    schedule_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resend_message_id: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ck_outreach_jobs_status",
        ),
        CheckConstraint(
            "current_step IS NULL OR current_step IN ('researching', 'personalizing', 'scheduling', 'complete')",
            name="ck_outreach_jobs_current_step",
        ),
        CheckConstraint(
            "send_status IN ('draft', 'approved', 'sent', 'bounced', 'replied')",
            name="ck_outreach_jobs_send_status",
        ),
        CheckConstraint(
            "data_confidence IS NULL OR data_confidence IN ('low', 'medium', 'high')",
            name="ck_outreach_jobs_data_confidence",
        ),
        Index("ix_outreach_jobs_user_id", "user_id"),
        Index("ix_outreach_jobs_user_id_created_at", "user_id", "created_at"),
        Index("ix_outreach_jobs_batch_id", "batch_id"),
        Index(
            "ix_outreach_jobs_status_running",
            "status",
            postgresql_where=text("status = 'running'"),
        ),
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User", back_populates="outreach_jobs", lazy="noload"
    )
    product_profile: Mapped[ProductProfile | None] = relationship(
        "ProductProfile", back_populates="outreach_jobs", lazy="noload"
    )
    batch: Mapped[BatchJob | None] = relationship(
        "BatchJob", back_populates="jobs", lazy="noload"
    )


# ---------------------------------------------------------------------------
# BatchJob — parent record for a multi-prospect batch run
# ---------------------------------------------------------------------------


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        TEXT,
        server_default=text("'running'"),
        nullable=False,
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    # Atomically incremented by graph nodes as prospects move through phases.
    research_done: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    personalize_done: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ck_batch_jobs_status",
        ),
        Index("ix_batch_jobs_user_id_created_at", "user_id", "created_at"),
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User", back_populates="batch_jobs", lazy="noload"
    )
    jobs: Mapped[list[OutreachJob]] = relationship(
        "OutreachJob", back_populates="batch", lazy="noload"
    )
