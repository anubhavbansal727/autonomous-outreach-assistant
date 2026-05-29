import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import update

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.db import IngestionJob


async def run_ingestion_job(ctx: dict, *, job_id: str, user_id: str, url: str) -> None:
    """ARQ job entry point for the ingestion graph.

    Writes current_step progress directly to the DB between nodes so that
    the polling endpoint always reflects the latest state.
    """
    async with AsyncSessionLocal() as db:
        async with db.begin():
            if settings.MOCK_MODE:
                await _run_mock_ingestion(db, job_id)
            else:
                await _run_real_ingestion(db, job_id, url)


async def _update_step(db, job_id: str, step: str) -> None:
    """Write current_step without committing the outer transaction."""
    await db.execute(
        update(IngestionJob)
        .where(IngestionJob.id == job_id)
        .values(current_step=step)
    )
    await db.flush()


async def _run_mock_ingestion(db, job_id: str) -> None:
    import pathlib

    fixtures_dir = pathlib.Path(__file__).parent.parent.parent / "fixtures"

    await _update_step(db, job_id, "scraping")
    await asyncio.sleep(2)

    await _update_step(db, job_id, "extracting")
    await asyncio.sleep(2)

    profile_data = json.loads((fixtures_dir / "product_profile.json").read_text())

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


async def _run_real_ingestion(db, job_id: str, url: str) -> None:
    from app.graphs.ingestion.graph import graph
    from app.graphs.ingestion.state import IngestionState

    try:
        await _update_step(db, job_id, "scraping")

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
                await _update_step(db, job_id, "extracting")
                await db.flush()

        final_state = last_event.get(last_node_name, {}) if last_node_name else {}

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
    except Exception as exc:
        await db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job_id)
            .values(status="failed", error_message=str(exc))
        )
        raise  # let ARQ apply retry policy
