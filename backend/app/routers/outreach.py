import csv
import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.db import BatchJob, OutreachJob, ProductProfile, User
from app.models.schemas import (
    BatchCreateResponse,
    BatchProspectStatus,
    BatchStatusResponse,
    DeleteJobResponse,
    EditDraftRequest,
    EditDraftResponse,
    GenerateRequest,
    GenerateResponse,
    HistoryItem,
    HistoryResponse,
    OutreachResultResponse,
    OutreachStatusResponse,
    RetryResponse,
    SendRequest,
    SendResponse,
)
from app.services.arq_pool import get_arq_pool
from app.services.rate_limiter import check_rate_limit
from app.services.resend import send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outreach", tags=["outreach"])


async def _get_active_profile(db: AsyncSession, user_id: uuid.UUID) -> ProductProfile:
    result = await db.execute(
        select(ProductProfile).where(
            ProductProfile.user_id == user_id,
            ProductProfile.is_active == True,  # noqa: E712
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "No active product profile", "code": "NO_ACTIVE_PROFILE"},
        )
    return profile


async def _get_job(
    db: AsyncSession, job_id: uuid.UUID, user_id: uuid.UUID
) -> OutreachJob:
    result = await db.execute(
        select(OutreachJob).where(
            OutreachJob.id == job_id,
            OutreachJob.user_id == user_id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Outreach job not found", "code": "JOB_NOT_FOUND"},
        )
    return job


def _profile_to_dict(profile: ProductProfile) -> dict:
    return {
        "product_name": profile.product_name,
        "one_liner": profile.one_liner,
        "target_customer": profile.target_customer,
        "pain_points": profile.pain_points,
        "differentiators": profile.differentiators,
        "case_studies": profile.case_studies,
        "cta": profile.cta,
        "icp": profile.icp,
        "avoid_messaging": profile.avoid_messaging,
        "source_url": profile.source_url,
    }


MAX_BATCH_PROSPECTS = 20


def _parse_prospects_csv(raw: bytes) -> list[GenerateRequest]:
    """Parse + validate an uploaded CSV into prospect rows.

    Requires a ``company_name`` column; ``contact_name`` is optional. Blank lines
    are skipped. Each row is validated through GenerateRequest (same sanitisation
    as the single-prospect endpoint). Raises 400 INVALID_CSV on any problem.
    """
    def _bad(msg: str):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": msg, "code": "INVALID_CSV"},
        )

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _bad("File must be UTF-8 encoded.")

    reader = csv.DictReader(io.StringIO(text))
    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    if "company_name" not in headers:
        raise _bad("CSV must have a 'company_name' column.")

    prospects: list[GenerateRequest] = []
    for line_no, row in enumerate(reader, start=2):
        norm = {
            (k or "").strip().lower(): (v.strip() if isinstance(v, str) else v)
            for k, v in row.items()
        }
        company = norm.get("company_name") or ""
        contact = norm.get("contact_name") or None
        if not company:
            continue  # skip blank rows
        try:
            prospects.append(
                GenerateRequest(company_name=company, contact_name=contact)
            )
        except ValidationError:
            raise _bad(f"Invalid row {line_no}: '{company}'.")
        if len(prospects) > MAX_BATCH_PROSPECTS:
            raise _bad(f"Batch is limited to {MAX_BATCH_PROSPECTS} prospects.")

    if not prospects:
        raise _bad("CSV contained no valid prospect rows.")
    return prospects


@router.post(
    "/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED
)
async def generate(
    body: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    pool = await get_arq_pool()

    allowed, retry_after = await check_rate_limit(
        pool,
        f"outreach:{current_user.id}",
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

    profile = await _get_active_profile(db, current_user.id)

    job = OutreachJob(
        user_id=current_user.id,
        company_name=body.company_name,
        contact_name=body.contact_name,
        status="running",
        product_profile_id=profile.id,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    await db.commit()

    await pool.enqueue_job(
        "run_outreach_job",
        job_id=str(job.id),
        user_id=str(current_user.id),
        company_name=body.company_name,
        contact_name=body.contact_name,
        product_profile=_profile_to_dict(profile),
    )

    return GenerateResponse(job_id=job.id)


@router.post(
    "/batch", response_model=BatchCreateResponse, status_code=status.HTTP_202_ACCEPTED
)
async def create_batch(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BatchCreateResponse:
    """Upload a CSV of up to 20 prospects and kick off a batch outreach run."""
    raw = await file.read()
    prospects = _parse_prospects_csv(raw)

    pool = await get_arq_pool()
    # Batches get their own quota, independent of the single-generate limit.
    allowed, retry_after = await check_rate_limit(
        pool,
        f"batch:{current_user.id}",
        limit=2,
        window=3600,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": f"Batch rate limit exceeded. Retry after {retry_after} seconds.",
                "code": "RATE_LIMIT_EXCEEDED",
            },
        )

    profile = await _get_active_profile(db, current_user.id)

    batch_id = uuid.uuid4()
    db.add(
        BatchJob(
            id=batch_id,
            user_id=current_user.id,
            product_profile_id=profile.id,
            status="running",
            total=len(prospects),
        )
    )

    payload: list[dict] = []
    for idx, p in enumerate(prospects):
        job_id = uuid.uuid4()
        db.add(
            OutreachJob(
                id=job_id,
                user_id=current_user.id,
                product_profile_id=profile.id,
                batch_id=batch_id,
                batch_index=idx,
                company_name=p.company_name,
                contact_name=p.contact_name,
                status="running",
                current_step="researching",
            )
        )
        payload.append(
            {
                "index": idx,
                "job_id": str(job_id),
                "company_name": p.company_name,
                "contact_name": p.contact_name,
            }
        )

    await db.commit()

    # Timeout (600s) and no-retry are configured on the worker via arq.func();
    # enqueue_job does not accept per-call _job_timeout/_max_tries.
    await pool.enqueue_job(
        "run_batch_job",
        batch_id=str(batch_id),
        user_id=str(current_user.id),
        prospects=payload,
        product_profile=_profile_to_dict(profile),
    )

    return BatchCreateResponse(batch_id=batch_id, total=len(prospects))


@router.get(
    "/batch/{batch_id}",
    response_model=BatchStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_batch_status(
    batch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BatchStatusResponse:
    result = await db.execute(
        select(BatchJob).where(
            BatchJob.id == batch_id,
            BatchJob.user_id == current_user.id,
        )
    )
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Batch not found", "code": "BATCH_NOT_FOUND"},
        )

    items_result = await db.execute(
        select(OutreachJob)
        .where(OutreachJob.batch_id == batch_id)
        .order_by(OutreachJob.batch_index)
    )
    jobs = items_result.scalars().all()

    return BatchStatusResponse(
        batch_id=batch.id,
        status=batch.status,
        total=batch.total,
        research_done=batch.research_done,
        personalize_done=batch.personalize_done,
        prospects=[
            BatchProspectStatus(
                job_id=j.id,
                company_name=j.company_name,
                contact_name=j.contact_name,
                status=j.status,
                current_step=j.current_step,
                send_status=j.send_status,
                data_confidence=j.data_confidence,
            )
            for j in jobs
        ],
        created_at=batch.created_at,
        completed_at=batch.completed_at,
    )


@router.get(
    "/status/{job_id}",
    response_model=OutreachStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_status(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OutreachStatusResponse:
    job = await _get_job(db, job_id, current_user.id)
    return OutreachStatusResponse(
        job_id=job.id,
        status=job.status,
        current_step=job.current_step,
        created_at=job.created_at,
    )


@router.get(
    "/result/{job_id}",
    response_model=OutreachResultResponse,
    status_code=status.HTTP_200_OK,
)
async def get_result(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OutreachResultResponse:
    job = await _get_job(db, job_id, current_user.id)

    if job.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Job not complete yet", "code": "JOB_RUNNING"},
        )

    return OutreachResultResponse(
        id=job.id,
        company_name=job.company_name,
        contact_name=job.contact_name,
        status=job.status,
        send_status=job.send_status,
        data_confidence=job.data_confidence,
        email_subject=job.email_subject,
        email_draft=job.email_draft,
        linkedin_draft=job.linkedin_draft,
        schedule_json=job.schedule_json,
        error_message=job.error_message,
        token_usage=job.token_usage,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.put(
    "/result/{job_id}",
    response_model=EditDraftResponse,
    status_code=status.HTTP_200_OK,
)
async def edit_draft(
    job_id: uuid.UUID,
    body: EditDraftRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EditDraftResponse:
    job = await _get_job(db, job_id, current_user.id)

    if job.send_status == "sent":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Cannot edit after send", "code": "ALREADY_SENT"},
        )

    if body.email_subject is not None:
        job.email_subject = body.email_subject
    if body.email_draft is not None:
        job.email_draft = body.email_draft
    if body.linkedin_draft is not None:
        job.linkedin_draft = body.linkedin_draft

    now = datetime.now(timezone.utc)
    await db.commit()

    return EditDraftResponse(updated_at=now)


@router.post(
    "/send/{job_id}",
    response_model=SendResponse,
    status_code=status.HTTP_200_OK,
)
async def send(
    job_id: uuid.UUID,
    body: SendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SendResponse:
    job = await _get_job(db, job_id, current_user.id)

    if job.send_status == "sent":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Already sent", "code": "ALREADY_SENT"},
        )

    # Load the user's active profile to get product_name and resend_domain
    result = await db.execute(
        select(ProductProfile).where(
            ProductProfile.user_id == current_user.id,
            ProductProfile.is_active == True,  # noqa: E712
        )
    )
    profile = result.scalar_one_or_none()

    # Fall back to resend.dev (Resend test domain) when the user hasn't
    # configured a verified sending domain yet.
    resend_domain = current_user.resend_domain or "resend.dev"

    product_name = profile.product_name if profile else "Our Product"

    try:
        message_id = await send_email(
            to_email=str(body.to_email),
            from_name=product_name,
            resend_domain=resend_domain,
            subject=job.email_subject or "(no subject)",
            body_text=job.email_draft or "",
        )
    except Exception as exc:
        logger.exception("Resend API call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": f"Email send failed: {exc}", "code": "SEND_FAILED"},
        )

    now = datetime.now(timezone.utc)
    job.send_status = "sent"
    job.resend_message_id = message_id
    job.sent_at = now
    await db.commit()

    return SendResponse(sent=True, resend_message_id=message_id, sent_at=now)


@router.post(
    "/retry/{job_id}",
    response_model=RetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RetryResponse:
    job = await _get_job(db, job_id, current_user.id)

    if job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Job is not in failed state", "code": "NOT_FAILED"},
        )

    pool = await get_arq_pool()

    allowed, retry_after = await check_rate_limit(
        pool,
        f"outreach:{current_user.id}",
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

    profile = await _get_active_profile(db, current_user.id)

    job.status = "running"
    job.current_step = None
    job.error_message = None
    job.retry_count = (job.retry_count or 0) + 1
    await db.commit()

    await pool.enqueue_job(
        "run_outreach_job",
        job_id=str(job.id),
        user_id=str(current_user.id),
        company_name=job.company_name,
        contact_name=job.contact_name,
        product_profile=_profile_to_dict(profile),
    )

    return RetryResponse(job_id=job.id, retry_count=job.retry_count)


@router.get(
    "/history",
    response_model=HistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HistoryResponse:
    offset = (page - 1) * per_page

    count_result = await db.execute(
        select(func.count()).select_from(OutreachJob).where(
            OutreachJob.user_id == current_user.id
        )
    )
    total: int = count_result.scalar_one()

    items_result = await db.execute(
        select(OutreachJob)
        .where(OutreachJob.user_id == current_user.id)
        .order_by(OutreachJob.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    jobs = items_result.scalars().all()

    return HistoryResponse(
        items=[HistoryItem.model_validate(j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.delete(
    "/{job_id}",
    response_model=DeleteJobResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeleteJobResponse:
    job = await _get_job(db, job_id, current_user.id)
    await db.delete(job)
    await db.commit()
    return DeleteJobResponse()
