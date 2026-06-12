"""db/session.py — how the app talks to PostgreSQL.

In plain English:
- ``engine`` is the connection pool to the database (created once, shared).
- ``AsyncSessionLocal`` is a factory: call it to get a fresh "session"
  (a unit of DB work you read/write through, then commit).
- ``get_db()`` is the FastAPI dependency used inside routers — it hands each
  request its own session and cleans it up afterwards.

Note: the background jobs (app/jobs/*) do NOT use ``get_db``; they open their
own ``AsyncSessionLocal()`` blocks because they run in the worker process,
outside of any web request.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[override]
    async with AsyncSessionLocal() as session:
        yield session
