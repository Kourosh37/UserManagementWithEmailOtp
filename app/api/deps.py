from typing import AsyncGenerator

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.auth import AuthService
from app.services.otp import OTPService, get_redis_client


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


def get_redis() -> Redis:
    return get_redis_client()


async def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> AsyncGenerator[AuthService, None]:
    otp_service = OTPService(redis)
    yield AuthService(session=session, otp_service=otp_service)
