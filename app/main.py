"""Application entrypoint for the OTP authentication service.

This module wires together the FastAPI application with its lifespan hooks,
database metadata, Redis cleanup, and CORS configuration. It is the root that
other modules depend on when the API process starts.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth_router
from app.core.config import settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import engine
from app.services.otp import close_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup and dispose shared clients on shutdown.

    Dependencies:
    - Uses the async SQLAlchemy engine from `app.db.session` to ensure the
      metadata defined in `app.db.base.Base` (and the imported models) exists.
    - Cleans up the Redis client via `close_redis_client` so connections are
      properly released when the FastAPI app stops.
    """

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_redis_client()
    await engine.dispose()


def create_application() -> FastAPI:
    """Assemble and configure the FastAPI application instance.

    - Injects the lifespan manager defined above to manage startup/shutdown.
    - Applies permissive CORS settings sourced from environment-driven `settings`.
    - Registers the authentication router that exposes OTP flows.
    """

    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # open for local/dev access via VPN/tun modes
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth_router)

    @application.get("/")
    async def healthcheck():
        """Lightweight health endpoint used by uptime monitors or the launcher."""
        return {"message": "Auth Service is running!"}

    return application


app = create_application()
