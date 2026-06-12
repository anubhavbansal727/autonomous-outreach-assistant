"""jobs/ingestion_job.py — the background job that turns a URL into a profile.

In plain English:
- This runs in the WORKER, not the web request. The /profile/ingest endpoint
  enqueues "run_ingestion_job"; ARQ calls the function below.
- It drives the ingestion LangGraph (app/graphs/ingestion/) which scrapes the
  site and uses an LLM to extract a product profile, then writes the result
  onto the IngestionJob database row.
- ``_update_step`` writes the current step ("scraping" → "extracting") to the DB
  in its own little transaction so the frontend's polling sees progress live.
- MOCK_MODE swaps the real LLM/scraper for canned fixture files — handy for
  demos and tests without spending API credits.

The "ctx" first argument is supplied by ARQ; we don't use it here.
"""

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import update

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.db import IngestionJob


async def run_ingestion_job(ctx: dict, *, job_id: str, user_id: str, url: str) -> None:
    """ARQ job entry point for the ingestion graph."""
    if settings.MOCK_MODE:
        await _run_mock_ingestion(job_id)
    else:
        await _run_real_ingestion(job_id, url)


async def _update_step(job_id: str, step: str) -> None:
    """Commit current_step in its own session so the polling API sees it immediately.

    Previously this shared the outer transaction and only called flush(), making
    step updates invisible to other DB connections until the whole job committed.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job_id)
            .values(current_step=step)
        )
        await db.commit()


async def _run_mock_ingestion(job_id: str) -> None:
    import pathlib

    fixtures_dir = pathlib.Path(__file__).parent.parent.parent / "fixtures"

    await _update_step(job_id, "scraping")
    await asyncio.sleep(2)

    await _update_step(job_id, "extracting")
    await asyncio.sleep(2)

    profile_data = json.loads((fixtures_dir / "product_profile.json").read_text(encoding="utf-8"))

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job_id)
            .values(
                status="done",
                current_step="complete",
                result_json=profile_data,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


async def _run_real_ingestion(job_id: str, url: str) -> None:
    from app.graphs.ingestion.graph import graph
    from app.graphs.ingestion.state import IngestionState

    try:
        await _update_step(job_id, "scraping")

        initial_state: IngestionState = {
            "url": url,
            "scraped_pages": [],
            "product_profile_output": None,
            "error": None,
        }

        last_node_name = None
        last_event: dict = {}

        async for event in graph.astream(initial_state, config={"recursion_limit": 5}):
            last_node_name = next(iter(event))
            last_event = event

            if last_node_name == "scrape_node":
                await _update_step(job_id, "extracting")

        final_state = last_event.get(last_node_name, {}) if last_node_name else {}

        async with AsyncSessionLocal() as db:
            if final_state.get("error"):
                await db.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(status="failed", error_message=final_state["error"])
                )
            else:
                await db.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(
                        status="done",
                        current_step="complete",
                        result_json=final_state.get("product_profile_output"),
                        completed_at=datetime.now(timezone.utc),
                    )
                )
            await db.commit()

    except Exception as exc:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(status="failed", error_message=str(exc))
            )
            await db.commit()
        raise  # let ARQ apply retry policy
