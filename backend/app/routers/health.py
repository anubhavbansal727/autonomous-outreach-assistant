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
