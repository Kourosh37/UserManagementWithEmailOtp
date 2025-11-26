from fastapi import APIRouter, Depends, status

from app.api import deps
from app.schemas.auth import Token, UserCreate, UserLogin
from app.schemas.common import Message
from app.schemas.otp import OTPRequest, OTPVerify
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=Message, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate,
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> Message:
    await auth_service.register(payload)
    return Message(message="Verification code sent to your email.")


@router.post("/verify-otp", response_model=Message)
async def verify_otp(
    payload: OTPVerify,
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> Message:
    await auth_service.verify_otp(payload)
    return Message(message="Account verified successfully.")


@router.post("/resend-otp", response_model=Message)
async def resend_otp(
    payload: OTPRequest,
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> Message:
    await auth_service.resend_otp(payload.email)
    return Message(message="A new verification code has been sent.")


@router.post("/login", response_model=Token)
async def login(
    payload: UserLogin,
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> Token:
    token = await auth_service.login(payload)
    return Token(access_token=token, token_type="bearer")
