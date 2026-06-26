"""main.py — the FastAPI application entry point ("the front door").

In plain English:
- This builds the web-server object (``app``) that answers HTTP requests from
  the React frontend.
- It turns on CORS (so the browser is allowed to call us) and registers every
  group of endpoints — auth, profile, outreach, crm, health — each of which
  lives in its own file under app/routers/.
- ``lifespan`` holds startup/shutdown hooks. On shutdown we close all database
  connections cleanly. (The database tables themselves are created by Alembic
  migrations, not here.)

Where it fits in the system: the browser talks to THIS process. Anything slow
or AI-heavy is NOT done inside a request here — it is handed off to the
background worker (see worker.py) so requests stay fast.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.dependencies import require_password_changed
from app.config import settings
from app.db.session import engine
from app.models.db import Base
from app.routers import auth, crm, health, members, outreach, profile, tenant


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

    # /auth is exempt from the forced-reset guard so a member who still owes a
    # password change can reach /auth/me, /auth/change-password and /auth/logout.
    app.include_router(auth.router)

    # Every other protected router is blocked (403 PASSWORD_CHANGE_REQUIRED)
    # until a forced reset is completed.
    protected = [Depends(require_password_changed)]
    app.include_router(profile.router, dependencies=protected)
    app.include_router(outreach.router, dependencies=protected)
    app.include_router(crm.router, dependencies=protected)
    app.include_router(members.router, dependencies=protected)
    app.include_router(tenant.router, dependencies=protected)

    app.include_router(health.router)

    return app


app = create_app()
