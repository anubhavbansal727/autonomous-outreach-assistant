"""Integration check for batch processing against a real Postgres.

Run with DATABASE_URL/REDIS_URL pointed at the dev stack. Verifies:
  A) the real Send() fan-out graph (LLM subgraphs stubbed) increments counters,
     fans in once, and writes per-prospect drafts; and
  B) the MOCK_MODE job path.

Cleans up all rows it creates.
"""
import asyncio
import json
import uuid

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal, bind_tenant_context
from app.models.db import BatchJob, Membership, OutreachJob, ProductProfile, Tenant, User


async def _seed(db, n: int) -> tuple[uuid.UUID, list[uuid.UUID]]:
    user = User(email=f"batchtest+{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    # Personal tenant reuses the user's UUID (same pattern as the rbac migration).
    await bind_tenant_context(db, tenant_id=user.id, user_id=user.id)
    db.add(Tenant(id=user.id, name="Batch Test Tenant"))
    db.add(Membership(tenant_id=user.id, user_id=user.id, role="owner"))
    profile = ProductProfile(tenant_id=user.id, created_by_user_id=user.id,
                             product_name="Test Product", is_active=True)
    db.add(profile)
    await db.flush()

    batch_id = uuid.uuid4()
    db.add(BatchJob(id=batch_id, tenant_id=user.id, user_id=user.id,
                    product_profile_id=profile.id, status="running", total=n))
    child_ids = []
    for i in range(n):
        jid = uuid.uuid4()
        child_ids.append(jid)
        db.add(OutreachJob(id=jid, tenant_id=user.id, user_id=user.id,
                           product_profile_id=profile.id,
                           batch_id=batch_id, batch_index=i, company_name=f"Company {i}",
                           status="running", current_step="researching"))
    await db.commit()
    return batch_id, child_ids, user.id


async def _cleanup(user_id):
    async with AsyncSessionLocal() as db:
        # tenant_id == user_id for rows seeded above
        await bind_tenant_context(db, tenant_id=user_id, user_id=user_id)
        await db.execute(delete(OutreachJob).where(OutreachJob.user_id == user_id))
        await db.execute(delete(BatchJob).where(BatchJob.user_id == user_id))
        await db.execute(delete(ProductProfile).where(ProductProfile.tenant_id == user_id))
        await db.execute(delete(Tenant).where(Tenant.id == user_id))  # cascades membership
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _assert_done(batch_id, n, label):
    async with AsyncSessionLocal() as db:
        batch = (await db.execute(select(BatchJob).where(BatchJob.id == batch_id))).scalar_one()
        children = (await db.execute(
            select(OutreachJob).where(OutreachJob.batch_id == batch_id)
            .order_by(OutreachJob.batch_index)
        )).scalars().all()
    assert batch.research_done == n, f"{label}: research_done={batch.research_done} != {n}"
    assert batch.personalize_done == n, f"{label}: personalize_done={batch.personalize_done} != {n}"
    assert batch.status == "done", f"{label}: batch.status={batch.status}"
    for c in children:
        assert c.status == "done", f"{label}: child {c.batch_index} status={c.status}"
        assert c.email_draft, f"{label}: child {c.batch_index} has no email_draft"
        assert c.current_step == "complete"
    print(f"  [{label}] OK — research={batch.research_done}/{n}, "
          f"personalize={batch.personalize_done}/{n}, all children done")


async def test_real_graph():
    """Real Send() fan-out + fan-in graph, with LLM subgraphs stubbed."""
    import app.graphs.batch.graph as bg

    class _Fake:
        def __init__(self, payload):
            self._p = payload
        async def ainvoke(self, state, config=None):
            return self._p

    bg.research_subgraph = _Fake({"research_output": "stubbed research findings"})
    bg.draft_subgraph = _Fake({
        "email_subject": "Hi from Test Product",
        "email_body": "Stubbed personalised body.",
        "linkedin_note": "Stubbed LI note.",
        "data_confidence": 0.85,
        "schedule_output": json.dumps({
            "send_at": "2026-06-09T09:30:00-05:00", "channel": "email",
            "recommended_window": "Tue 9-10am", "flag_for_human": False, "reason": "ok",
        }),
    })

    from app.jobs.batch_job import _run_real_batch

    n = 4
    async with AsyncSessionLocal() as db:
        batch_id, child_ids, user_id = await _seed(db, n)
    try:
        prospects = [{"index": i, "job_id": str(cid), "company_name": f"Company {i}",
                      "contact_name": ""} for i, cid in enumerate(child_ids)]
        # tenant_id == user_id for rows created by _seed.
        await _run_real_batch(str(batch_id), str(user_id), prospects, {"product_name": "Test Product"})
        await _assert_done(batch_id, n, "real-graph")
    finally:
        await _cleanup(user_id)


async def test_mock_path():
    from app.jobs.batch_job import _run_mock_batch

    n = 3
    async with AsyncSessionLocal() as db:
        batch_id, child_ids, user_id = await _seed(db, n)
    try:
        prospects = [{"index": i, "job_id": str(cid)} for i, cid in enumerate(child_ids)]
        await _run_mock_batch(str(batch_id), str(user_id), prospects)
        await _assert_done(batch_id, n, "mock-path")
    finally:
        await _cleanup(user_id)


async def main():
    await test_real_graph()
    await test_mock_path()
    print("ALL BATCH INTEGRATION CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
