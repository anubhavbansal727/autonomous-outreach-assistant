"""routers/health.py — a tiny "are you alive?" endpoint (/health).

In plain English:
- Hosting platforms (Railway) ping ``GET /health`` repeatedly. If it stops
  returning 200, they assume the app crashed and restart it.
- It deliberately does NO database or Redis check and returns instantly — see
  the function docstring for why touching the DB here causes false alarms.
"""

from fastapi import APIRouter

from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """
    Liveness probe — confirms the process is alive and the event loop is running.
    Returns 200 instantly with no I/O so Railway's health check always passes.

    DB / Redis connectivity is intentionally not checked here: the first
    asyncpg connection can take 10-30 s on Railway's cold network, which
    exceeds the default health-check timeout and causes false failures.
    """
    return HealthResponse(status="ok", db="ok", redis="ok")
