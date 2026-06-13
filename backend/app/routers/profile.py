"""routers/profile.py — managing the user's "what I'm selling" profile (/profile).

In plain English, two things happen here:
1) INGESTION: ``POST /ingest`` takes a company website URL and kicks off a
   background job (run_ingestion_job) that scrapes the site and uses an LLM to
   draft a structured product profile. The endpoint returns immediately with a
   job_id; the frontend polls ``GET /result/{job_id}`` until it's done.
2) PROFILE CRUD: ``GET ""`` reads the active profile, ``POST /save`` stores one
   (deactivating any previous one — each TENANT has exactly one active
   profile, shared by all its members), ``PUT /update`` edits it.
The saved profile is later fed into every outreach email so the AI knows what
the company sells.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import RequestContext, require_permission
from app.auth.permissions import Permission
from app.db.session import get_db
from app.models.db import IngestionJob, ProductProfile
from app.models.schemas import (
    IngestRequest,
    IngestResponse,
    IngestionResultResponse,
    ProfileResponse,
    SaveProfileRequest,
    SaveProfileResponse,
    UpdateProfileRequest,
    UpdateProfileResponse,
)
from app.services.arq_pool import get_arq_pool
from app.services.rate_limiter import check_rate_limit

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
async def get_profile(
    ctx: RequestContext = Depends(require_permission(Permission.PROFILE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    result = await db.execute(
        select(ProductProfile).where(
            ProductProfile.tenant_id == ctx.tenant_id,
            ProductProfile.is_active == True,  # noqa: E712
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "No active profile found", "code": "NO_ACTIVE_PROFILE"},
        )
    return ProfileResponse(
        profile_id=profile.id,
        product_name=profile.product_name,
        one_liner=profile.one_liner,
        target_customer=profile.target_customer,
        pain_points=profile.pain_points or [],
        differentiators=profile.differentiators or [],
        case_studies=profile.case_studies or [],
        cta=profile.cta,
        icp=profile.icp,
        avoid_messaging=profile.avoid_messaging,
        source_url=profile.source_url,
        updated_at=profile.updated_at,
    )


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    body: IngestRequest,
    ctx: RequestContext = Depends(require_permission(Permission.PROFILE_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    pool = await get_arq_pool()

    # Rate limit: 10 ingest requests per hour per user
    allowed, retry_after = await check_rate_limit(
        pool,  # arq pool is itself an async Redis client
        f"ingest:{ctx.user.id}",
        limit=10,
        window=3600,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": f"Rate limit exceeded. Retry after {retry_after} seconds.",
                "code": "RATE_LIMIT_EXCEEDED",
            },
        )

    job = IngestionJob(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user.id,
        url=body.url,
        status="running",
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    await db.commit()

    await pool.enqueue_job(
        "run_ingestion_job",
        job_id=str(job.id),
        user_id=str(ctx.user.id),
        tenant_id=str(ctx.tenant_id),
        url=body.url,
    )

    return IngestResponse(job_id=job.id)


@router.get(
    "/result/{job_id}",
    response_model=IngestionResultResponse,
    status_code=status.HTTP_200_OK,
)
async def get_ingestion_result(
    job_id: uuid.UUID,
    ctx: RequestContext = Depends(require_permission(Permission.PROFILE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> IngestionResultResponse:
    # Ingestion jobs are tenant-shared config work, not private per member.
    result = await db.execute(
        select(IngestionJob).where(
            IngestionJob.id == job_id,
            IngestionJob.tenant_id == ctx.tenant_id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Ingestion job not found", "code": "JOB_NOT_FOUND"},
        )

    return IngestionResultResponse(
        job_id=job.id,
        status=job.status,
        current_step=job.current_step,
        profile=job.result_json,
        error_message=job.error_message,
    )


@router.post("/save", response_model=SaveProfileResponse, status_code=status.HTTP_201_CREATED)
async def save_profile(
    body: SaveProfileRequest,
    ctx: RequestContext = Depends(require_permission(Permission.PROFILE_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> SaveProfileResponse:
    # Deactivate any existing active profile for this tenant
    await db.execute(
        update(ProductProfile)
        .where(
            ProductProfile.tenant_id == ctx.tenant_id,
            ProductProfile.is_active == True,  # noqa: E712
        )
        .values(is_active=False)
    )

    profile = ProductProfile(
        tenant_id=ctx.tenant_id,
        created_by_user_id=ctx.user.id,
        product_name=body.product_name,
        one_liner=body.one_liner,
        target_customer=body.target_customer,
        pain_points=body.pain_points,
        differentiators=body.differentiators,
        case_studies=body.case_studies,
        cta=body.cta,
        icp=body.icp,
        avoid_messaging=body.avoid_messaging,
        source_url=body.source_url,
        is_active=True,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    await db.commit()

    return SaveProfileResponse(profile_id=profile.id)


@router.put("/update", response_model=UpdateProfileResponse, status_code=status.HTTP_200_OK)
async def update_profile(
    body: UpdateProfileRequest,
    ctx: RequestContext = Depends(require_permission(Permission.PROFILE_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> UpdateProfileResponse:
    result = await db.execute(
        select(ProductProfile).where(
            ProductProfile.tenant_id == ctx.tenant_id,
            ProductProfile.is_active == True,  # noqa: E712
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "No active profile found", "code": "NO_ACTIVE_PROFILE"},
        )

    # Apply only the non-None fields from the request
    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    now = datetime.now(timezone.utc)
    profile.updated_at = now

    await db.commit()

    return UpdateProfileResponse(profile_id=profile.id, updated_at=now)
