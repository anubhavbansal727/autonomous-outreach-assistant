"""BatchGraph — dynamic fan-out / fan-in over the existing OutreachGraph nodes.

Topology
--------

    START
      │
      ▼
   dispatch ──Send("research_one", task) × N──►  research_one  (parallel, capped by
      │                                            │            max_concurrency at call time)
      │                                            │  runs research_subgraph (ReAct loop)
      │                                            │  atomically ++batch.research_done
      │                                            ▼
      │                                  research_results (reducer accumulates)
      │                                            │  fan-in
      ▼                                            ▼
                                        personalize_sequential  (runs ONCE)
                                            for each prospect, in order:
                                              run draft_subgraph (personalize→schedule→extract)
                                              write child OutreachJob row
                                              ++batch.personalize_done
                                            │
                                            ▼
                                           END

Reuse
-----
This module does NOT redefine any agent logic. It composes the node functions
and route functions already defined in app/graphs/outreach/graph.py into two
small compiled subgraphs (research-only and draft-only) and orchestrates them
with Send().

DB writes inside nodes
----------------------
Unlike the single-prospect flow (where the ARQ wrapper owns DB writes), the
batch nodes write progress directly. Per-item progress is finer-grained than
astream's superstep granularity, so the live "Research X/N · Personalizing Y/N"
counters must be updated from inside the nodes. Counter increments use atomic
``col = col + 1`` SQL so concurrent research branches don't clobber each other.
"""

import json
import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langgraph.constants import Send
from langgraph.graph import END, START, StateGraph
from sqlalchemy import update

from app.db.session import AsyncSessionLocal
from app.graphs.outreach.graph import (
    extract_schedule_node,
    personalize_node,
    research_node,
    research_tools_node,
    route_after_research,
    route_after_schedule,
    schedule_node,
    schedule_tools_node,
)
from app.graphs.outreach.state import OutreachState
from app.models.db import BatchJob, OutreachJob

from .state import BatchState, ResearchTask

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reusable subgraphs built from the existing outreach nodes
# ---------------------------------------------------------------------------

# Research-only ReAct loop: same as the outreach graph's research phase, but the
# "no more tool calls" branch terminates at END instead of personalize_node.
_research_builder = StateGraph(OutreachState)
_research_builder.add_node("research_node", research_node)
_research_builder.add_node("research_tools_node", research_tools_node)
_research_builder.add_edge(START, "research_node")
_research_builder.add_conditional_edges(
    "research_node",
    route_after_research,
    {"research_tools_node": "research_tools_node", "personalize_node": END},
)
_research_builder.add_edge("research_tools_node", "research_node")
research_subgraph = _research_builder.compile()

# Draft-only flow: personalize → schedule ReAct loop → extract. Seeded with
# research_output already populated and a fresh message list (focused context).
_draft_builder = StateGraph(OutreachState)
_draft_builder.add_node("personalize_node", personalize_node)
_draft_builder.add_node("schedule_node", schedule_node)
_draft_builder.add_node("schedule_tools_node", schedule_tools_node)
_draft_builder.add_node("extract_schedule_node", extract_schedule_node)
_draft_builder.add_edge(START, "personalize_node")
_draft_builder.add_edge("personalize_node", "schedule_node")
_draft_builder.add_conditional_edges(
    "schedule_node",
    route_after_schedule,
    {
        "schedule_tools_node": "schedule_tools_node",
        "extract_schedule_node": "extract_schedule_node",
    },
)
_draft_builder.add_edge("schedule_tools_node", "schedule_node")
_draft_builder.add_edge("extract_schedule_node", END)
draft_subgraph = _draft_builder.compile()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _confidence_tier(raw: object) -> str:
    """Map a 0.0–1.0 float confidence to the DB enum tier (mirrors outreach_job)."""
    if isinstance(raw, float):
        if raw >= 0.7:
            return "high"
        if raw >= 0.4:
            return "medium"
        return "low"
    return str(raw) if raw else "low"


def _base_outreach_state(
    company_name: str, contact_name: str, product_profile: str, avoid_messaging: str
) -> OutreachState:
    return {
        "messages": [
            HumanMessage(content=f"Research {company_name} for B2B outreach")
        ],
        "company_name": company_name,
        "contact_name": contact_name or "",
        "company_url": "",
        "product_profile": product_profile,
        "research_output": "",
        "email_subject": "",
        "email_body": "",
        "linkedin_note": "",
        "data_confidence": 0.0,
        "personalization_signals": [],
        "schedule_output": "",
        "avoid_messaging": avoid_messaging or "",
    }


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def dispatch(state: BatchState) -> dict:
    """No-op staging node; the fan-out happens in the conditional edge below."""
    return {}


def route_to_research(state: BatchState) -> list[Send]:
    """Dynamic fan-out: one parallel research branch per prospect (Send API)."""
    return [Send("research_one", task) for task in state["prospects"]]


async def research_one(task: ResearchTask) -> dict:
    """Run the research ReAct loop for a single prospect (one parallel branch)."""
    sub_state = _base_outreach_state(
        task["company_name"],
        task["contact_name"],
        task["product_profile"],
        task["avoid_messaging"],
    )
    result = await research_subgraph.ainvoke(
        sub_state, config={"recursion_limit": 25}
    )
    research_output = result.get("research_output", "") or ""

    # Atomic increment — safe under concurrent branches.
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(BatchJob)
            .where(BatchJob.id == task["batch_id"])
            .values(research_done=BatchJob.research_done + 1)
        )
        await db.commit()

    return {
        "research_results": [
            {
                "index": task["index"],
                "job_id": task["job_id"],
                "company_name": task["company_name"],
                "contact_name": task["contact_name"],
                "research_output": research_output,
            }
        ]
    }


async def personalize_sequential(state: BatchState) -> dict:
    """Fan-in: personalise + schedule each prospect sequentially, in CSV order."""
    batch_id = state["batch_id"]
    product_profile = state["product_profile"]
    avoid_messaging = state["avoid_messaging"]

    for res in sorted(state["research_results"], key=lambda r: r["index"]):
        job_id = res["job_id"]

        # Mark this child as actively personalising so the per-prospect table updates.
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(OutreachJob)
                .where(OutreachJob.id == job_id)
                .values(current_step="personalizing")
            )
            await db.commit()

        sub_state = _base_outreach_state(
            res["company_name"], res["contact_name"], product_profile, avoid_messaging
        )
        sub_state["messages"] = []
        sub_state["research_output"] = res["research_output"]

        try:
            draft = await draft_subgraph.ainvoke(
                sub_state, config={"recursion_limit": 25}
            )
        except Exception as exc:  # noqa: BLE001 — isolate per-prospect failures
            logger.exception("Personalisation failed for batch child %s", job_id)
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(OutreachJob)
                    .where(OutreachJob.id == job_id)
                    .values(status="failed", error_message=str(exc)[:1000])
                )
                await db.commit()
            continue

        schedule_json = None
        raw_schedule = draft.get("schedule_output")
        if raw_schedule:
            try:
                schedule_json = json.loads(raw_schedule)
            except Exception:  # noqa: BLE001
                schedule_json = None

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(OutreachJob)
                .where(OutreachJob.id == job_id)
                .values(
                    status="done",
                    current_step="complete",
                    email_subject=draft.get("email_subject") or None,
                    email_draft=draft.get("email_body") or None,
                    linkedin_draft=draft.get("linkedin_note") or None,
                    data_confidence=_confidence_tier(draft.get("data_confidence", 0.0)),
                    schedule_json=schedule_json,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.execute(
                update(BatchJob)
                .where(BatchJob.id == batch_id)
                .values(personalize_done=BatchJob.personalize_done + 1)
            )
            await db.commit()

    return {}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

_builder = StateGraph(BatchState)
_builder.add_node("dispatch", dispatch)
_builder.add_node("research_one", research_one)
_builder.add_node("personalize_sequential", personalize_sequential)

_builder.add_edge(START, "dispatch")
_builder.add_conditional_edges("dispatch", route_to_research, ["research_one"])
# Fan-in: LangGraph runs personalize_sequential once after all research branches.
_builder.add_edge("research_one", "personalize_sequential")
_builder.add_edge("personalize_sequential", END)

graph = _builder.compile()
