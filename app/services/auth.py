"""Authentication domain logic orchestrating users, OTP, and JWT issuance."""

from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.models.user import User
from app.schemas.auth import UserCreate, UserLogin
from app.schemas.otp import OTPVerify
from app.services.email import send_otp_email
from app.services.oauth import OAuthProfile
from app.services.otp import OTPService


class AuthService:
    """High-level service used by API routes; holds DB session and OTP service."""

    def __init__(self, session: AsyncSession, otp_service: OTPService):
        """Inject dependencies so the service can hit both the DB and Redis."""
        self.session = session
        self.otp_service = otp_service

    async def _get_user_by_email(self, email: str) -> User | None:
        """Fetch a user by email; shared helper to avoid repeated query code."""
        return await self.session.scalar(select(User).where(User.email == email))

    async def register(self, payload: UserCreate) -> User:
        """Create a user, hash their password, and send an OTP for verification.

        Dependencies:
        - SQLAlchemy session for persistence
        - OTPService to mint a code stored in Redis
        - `send_otp_email` to deliver the code via SMTP
        """

        existing_user = await self._get_user_by_email(payload.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists.",
            )

        user = User(
            email=payload.email,
            hashed_password=get_password_hash(payload.password),
            auth_provider="local",
            is_active=False,
            is_verified=False,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        otp_code = await self.otp_service.issue_otp(user.email)
        sent, err = await send_otp_email(user.email, otp_code)
        if not sent:
            await self.otp_service.invalidate(user.email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send verification code. Please check SMTP settings. ({err})",
            )

        return user

    async def verify_otp(self, payload: OTPVerify) -> User:
        """Validate a submitted code and activate the corresponding user."""

        user = await self._get_user_by_email(payload.email)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        is_valid = await self.otp_service.validate_otp(payload.email, payload.code)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification code.",
            )

        user.is_verified = True
        user.is_active = True
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def resend_otp(self, email: str) -> None:
        """Issue and send a fresh OTP for a user needing another email."""

        user = await self._get_user_by_email(email)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        otp_code = await self.otp_service.issue_otp(email)
        sent, err = await send_otp_email(email, otp_code)
        if not sent:
            await self.otp_service.invalidate(email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send verification code. Please check SMTP settings. ({err})",
            )

    async def login(self, payload: UserLogin) -> str:
        """Authenticate a verified user and mint a short-lived JWT access token."""

        user = await self._get_user_by_email(payload.email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
            )

        if user.auth_provider != "local":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This account uses social login. Sign in with Google or GitHub.",
            )

        if not user.hashed_password or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
            )

        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not verified. Please complete the OTP flow.",
            )

        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        return create_access_token(subject=user.email, expires_delta=expires_delta)

    async def login_with_oauth(self, profile: OAuthProfile) -> str:
        """Create or update a user based on OAuth provider profile and return JWT."""

        if not profile.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address not provided by OAuth provider. Cannot proceed.",
            )

        user = await self._get_user_by_email(profile.email)

        if user:
            if user.auth_provider != profile.provider:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Account exists with a different sign-in method. Use your original provider.",
                )
            if user.provider_id and user.provider_id != profile.provider_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OAuth provider id mismatch for this account.",
                )

            user.provider_id = user.provider_id or profile.provider_id
            user.is_verified = True
            user.is_active = True
            await self.session.commit()
            await self.session.refresh(user)
        else:
            user = User(
                email=profile.email,
                hashed_password=None,
                auth_provider=profile.provider,
                provider_id=profile.provider_id,
                is_active=True,
                is_verified=True,
            )
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)

        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        return create_access_token(subject=user.email, expires_delta=expires_delta)
