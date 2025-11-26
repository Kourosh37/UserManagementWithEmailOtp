"""Dependency providers used by FastAPI endpoints.

These helpers expose database sessions, Redis clients, and composed services
through FastAPI's dependency injection system so route handlers remain thin.
"""

from typing import AsyncGenerator

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.auth import AuthService
from app.services.otp import OTPService, get_redis_client


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session tied to the shared engine."""

    async for session in get_session():
        yield session


def get_redis() -> Redis:
    """Return a singleton Redis client used for OTP storage."""
    return get_redis_client()


async def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> AsyncGenerator[AuthService, None]:
    """Assemble AuthService with its database session and Redis-backed OTP service.

    Dependencies:
    - `AsyncSession` from `get_db_session` for user persistence.
    - `Redis` client from `get_redis` for OTP issuance/validation.
    """

    otp_service = OTPService(redis)
    yield AuthService(session=session, otp_service=otp_service)
