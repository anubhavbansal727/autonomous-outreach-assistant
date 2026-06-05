from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import engine
from app.models.db import Base
from app.routers import auth, crm, health, outreach, profile


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Alembic handles schema — nothing to do here
    yield
    # Shutdown: release all DB connections
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Mini CRM AI Crew", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(outreach.router)
    app.include_router(crm.router)
    app.include_router(health.router)

    return app


app = create_app()
