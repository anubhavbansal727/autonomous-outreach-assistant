"""jobs/batch_job.py — the background job for a whole CSV of prospects.

In plain English:
- Runs in the WORKER. The /outreach/batch endpoint uploads a CSV, creates one
  BatchJob parent row plus one child OutreachJob per prospect, then enqueues
  "run_batch_job"; ARQ calls the function below.
- It drives the BATCH LangGraph (app/graphs/batch/) which researches all
  prospects in PARALLEL, then writes a personalised draft for each one.
- Unlike the single-outreach job, here the GRAPH NODES write progress to the DB
  themselves (the per-prospect counters), so this wrapper mostly just runs the
  graph to completion and then marks the whole batch "done".
- On failure it marks both the batch AND any still-"running" children as
  "failed", so no prospect is left stuck forever. Remember: this job is
  configured with NO retries (see worker.py) so a half-done batch isn't redone.
"""

import asyncio
import json
import logging
import pathlib
from datetime import datetime, timezone

from sqlalchemy import update

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.db import BatchJob, OutreachJob

logger = logging.getLogger(__name__)


async def run_batch_job(
    ctx: dict,
    *,
    batch_id: str,
    user_id: str,
    prospects: list[dict],
    product_profile: dict,
) -> None:
    """ARQ entry point for a multi-prospect batch run.

    Enqueued with _max_tries=1 and a long _job_timeout: a partially-completed
    batch must not restart from scratch, and a 20-prospect run can exceed the
    default 120s worker timeout.
    """
    if settings.MOCK_MODE:
        await _run_mock_batch(batch_id, prospects)
    else:
        await _run_real_batch(batch_id, prospects, product_profile)


async def _mark_batch(batch_id: str, **values) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(BatchJob).where(BatchJob.id == batch_id).values(**values)
        )
        await db.commit()


async def _run_real_batch(
    batch_id: str, prospects: list[dict], product_profile: dict
) -> None:
    from app.graphs.batch.graph import graph
    from app.graphs.batch.state import BatchState

    avoid_messaging = product_profile.get("avoid_messaging", "") or ""
    product_profile_json = json.dumps(product_profile)

    tasks = [
        {
            "index": p["index"],
            "job_id": str(p["job_id"]),
            "company_name": p["company_name"],
            "contact_name": p.get("contact_name") or "",
            "batch_id": batch_id,
            "product_profile": product_profile_json,
            "avoid_messaging": avoid_messaging,
        }
        for p in prospects
    ]

    initial_state: BatchState = {
        "batch_id": batch_id,
        "product_profile": product_profile_json,
        "avoid_messaging": avoid_messaging,
        "prospects": tasks,
        "research_results": [],
    }

    config = {
        # Cap parallel research branches — each may spawn Playwright/Serper —
        # while still using Send() dynamic fan-out.
        "max_concurrency": 5,
        "recursion_limit": 50,
        "run_name": f"batch-job-{batch_id[:8]}",
        "tags": ["batch"],
    }

    try:
        # The nodes write all per-prospect progress + drafts to the DB directly;
        # we just drive the graph to completion here.
        async for _ in graph.astream(initial_state, config=config):
            pass

        await _mark_batch(
            batch_id, status="done", completed_at=datetime.now(timezone.utc)
        )
    except Exception as exc:
        logger.exception("Batch job %s failed", batch_id)
        try:
            async with AsyncSessionLocal() as db:
                # Don't strand any child as forever-running.
                await db.execute(
                    update(OutreachJob)
                    .where(
                        OutreachJob.batch_id == batch_id,
                        OutreachJob.status == "running",
                    )
                    .values(status="failed", error_message=str(exc)[:1000])
                )
                await db.execute(
                    update(BatchJob)
                    .where(BatchJob.id == batch_id)
                    .values(
                        status="failed",
                        error_message=str(exc)[:1000],
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
        except Exception:
            logger.exception("Failed to mark batch %s as failed", batch_id)
        raise


async def _run_mock_batch(batch_id: str, prospects: list[dict]) -> None:
    """Fixture-driven batch for MOCK_MODE: increment counters with delays."""
    fixtures_dir = pathlib.Path(__file__).parent.parent.parent / "fixtures"
    draft = json.loads((fixtures_dir / "outreach_draft.json").read_text(encoding="utf-8"))
    schedule = json.loads((fixtures_dir / "schedule_output.json").read_text(encoding="utf-8"))

    ordered = sorted(prospects, key=lambda p: p["index"])

    # Parallel research phase — counter climbs to total.
    for _ in ordered:
        await asyncio.sleep(1)
        await _mark_batch(batch_id, research_done=BatchJob.research_done + 1)

    # Sequential personalisation phase — write each child + climb the counter.
    for p in ordered:
        job_id = str(p["job_id"])
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(OutreachJob)
                .where(OutreachJob.id == job_id)
                .values(current_step="personalizing")
            )
            await db.commit()
        await asyncio.sleep(1)
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(OutreachJob)
                .where(OutreachJob.id == job_id)
                .values(
                    status="done",
                    current_step="complete",
                    email_subject=draft.get("email_subject"),
                    email_draft=draft.get("email_body"),
                    linkedin_draft=draft.get("linkedin_note"),
                    data_confidence=draft.get("data_confidence", "medium"),
                    schedule_json=schedule,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.execute(
                update(BatchJob)
                .where(BatchJob.id == batch_id)
                .values(personalize_done=BatchJob.personalize_done + 1)
            )
            await db.commit()

    await _mark_batch(
        batch_id, status="done", completed_at=datetime.now(timezone.utc)
    )
