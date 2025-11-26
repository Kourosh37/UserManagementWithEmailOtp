"""OTP issuance and validation utilities backed by Redis."""

import secrets
from typing import Optional

from redis.asyncio import Redis

from app.core.config import settings


_redis_client: Optional[Redis] = None


def get_redis_client() -> Redis:
    """Return a lazily initialized Redis client shared across the service."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    """Close the shared Redis client; invoked during application shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


def _otp_key(email: str) -> str:
    """Generate the Redis key that scopes an OTP to a user's email."""
    return f"otp:{email}"


def generate_otp(length: int = settings.OTP_LENGTH) -> str:
    """Create a zero-padded numeric OTP with configurable length."""
    upper_bound = 10 ** length
    return f"{secrets.randbelow(upper_bound):0{length}d}"


class OTPService:
    """High-level API for issuing, validating, and invalidating OTP codes."""

    def __init__(self, redis_client: Redis):
        """Receive a Redis client (injected by FastAPI dependency graph)."""
        self.redis = redis_client

    async def issue_otp(self, email: str) -> str:
        """Store a newly generated OTP in Redis with an expiry."""
        code = generate_otp()
        await self.redis.set(_otp_key(email), code, ex=settings.OTP_EXPIRE_SECONDS)
        return code

    async def validate_otp(self, email: str, code: str) -> bool:
        """Check the submitted code and delete it to enforce single use."""
        stored = await self.redis.get(_otp_key(email))
        if stored is None or stored != code:
            return False
        await self.redis.delete(_otp_key(email))
        return True

    async def invalidate(self, email: str) -> None:
        """Remove an OTP without validation (used after failed email sends)."""
        await self.redis.delete(_otp_key(email))
