import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import update

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.db import OutreachJob

# Mapping from LangGraph node name to the DB current_step value
_NODE_STEP_MAP: dict[str, str] = {
    "research_node": "researching",
    "personalize_node": "personalizing",
    "schedule_node": "scheduling",
}


async def run_outreach_job(
    ctx: dict,
    *,
    job_id: str,
    user_id: str,
    company_name: str,
    contact_name: str | None,
    product_profile: dict,
) -> None:
    """ARQ job entry point for the outreach graph."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            if settings.MOCK_MODE:
                await _run_mock_outreach(db, job_id)
            else:
                await _run_real_outreach(
                    db, job_id, company_name, contact_name, product_profile
                )


async def _update_step(db, job_id: str, step: str) -> None:
    await db.execute(
        update(OutreachJob)
        .where(OutreachJob.id == job_id)
        .values(current_step=step)
    )
    await db.flush()


async def _run_mock_outreach(db, job_id: str) -> None:
    import pathlib

    fixtures_dir = pathlib.Path(__file__).parent.parent.parent / "fixtures"

    for step in ("researching", "personalizing", "scheduling"):
        await _update_step(db, job_id, step)
        await asyncio.sleep(2)

    draft = json.loads((fixtures_dir / "outreach_draft.json").read_text())
    schedule = json.loads((fixtures_dir / "schedule_output.json").read_text())

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


async def _run_real_outreach(
    db,
    job_id: str,
    company_name: str,
    contact_name: str | None,
    product_profile: dict,
) -> None:
    from langchain_core.messages import HumanMessage

    from app.graphs.outreach.graph import graph
    from app.graphs.outreach.state import OutreachState

    try:
        initial_state: OutreachState = {
            "messages": [
                HumanMessage(
                    content=f"Research {company_name} for B2B outreach"
                )
            ],
            "company_name": company_name,
            "contact_name": contact_name or "",
            "company_url": "",
            "product_profile": json.dumps(product_profile),
            "research_output": "",
            "email_subject": "",
            "email_body": "",
            "linkedin_note": "",
            "data_confidence": 0.0,
            "personalization_signals": [],
            "schedule_output": "",
            "avoid_messaging": product_profile.get("avoid_messaging", "") or "",
        }

        last_node_name: str | None = None
        last_event: dict = {}

        # run_name must NOT contain contact_name or prospect email (CLAUDE.md rule #5).
        # We use a generic identifier so LangSmith traces are PII-free.
        langsmith_config = {
            "recursion_limit": 25,
            "run_name": f"outreach-job-{job_id[:8]}",
            "tags": ["outreach"],
        }
        async for event in graph.astream(initial_state, config=langsmith_config):
            last_node_name = next(iter(event))
            last_event = event

            if last_node_name in _NODE_STEP_MAP:
                await _update_step(db, job_id, _NODE_STEP_MAP[last_node_name])

        final_state = (
            last_event.get(last_node_name, {}) if last_node_name else {}
        )

        # Convert float confidence to the DB enum tier
        raw_confidence = final_state.get("data_confidence", 0.0)
        if isinstance(raw_confidence, float):
            if raw_confidence >= 0.7:
                confidence_str = "high"
            elif raw_confidence >= 0.4:
                confidence_str = "medium"
            else:
                confidence_str = "low"
        else:
            confidence_str = str(raw_confidence) if raw_confidence else "low"

        schedule_json: dict | None = None
        raw_schedule = final_state.get("schedule_output")
        if raw_schedule:
            try:
                schedule_json = json.loads(raw_schedule)
            except Exception:
                pass

        await db.execute(
            update(OutreachJob)
            .where(OutreachJob.id == job_id)
            .values(
                status="done",
                current_step="complete",
                email_subject=final_state.get("email_subject") or None,
                email_draft=final_state.get("email_body") or None,
                linkedin_draft=final_state.get("linkedin_note") or None,
                data_confidence=confidence_str,
                schedule_json=schedule_json,
                completed_at=datetime.now(timezone.utc),
            )
        )
    except Exception as exc:
        await db.execute(
            update(OutreachJob)
            .where(OutreachJob.id == job_id)
            .values(
                status="failed",
                error_message=str(exc),
                retry_count=OutreachJob.retry_count + 1,
            )
        )
        raise  # let ARQ apply retry policy
