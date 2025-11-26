"""HTTP route handlers for authentication and OTP operations."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.schemas.auth import OAuthCallbackRequest, OAuthStartResponse, OAuthToken, Token, UserCreate, UserLogin
from app.schemas.common import Message
from app.schemas.otp import OTPRequest, OTPVerify
from app.services.auth import AuthService
from app.services.oauth import OAuthService, OAuthProvider

router = APIRouter(prefix="/auth", tags=["authentication"])


def _normalize_provider(provider: str) -> OAuthProvider:
    """Validate and normalize provider path parameter."""
    provider_l = provider.lower()
    if provider_l not in ("google", "github"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported OAuth provider.")
    return provider_l  # type: ignore[return-value]


@router.post("/register", response_model=Message, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate,
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> Message:
    """Create a new user record and dispatch an OTP email for verification."""

    await auth_service.register(payload)
    return Message(message="Verification code sent to your email.")


@router.post("/verify-otp", response_model=Message)
async def verify_otp(
    payload: OTPVerify,
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> Message:
    """Confirm an email address using the submitted OTP code."""

    await auth_service.verify_otp(payload)
    return Message(message="Account verified successfully.")


@router.post("/resend-otp", response_model=Message)
async def resend_otp(
    payload: OTPRequest,
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> Message:
    """Issue a fresh OTP to the given email address."""

    await auth_service.resend_otp(payload.email)
    return Message(message="A new verification code has been sent.")


@router.post("/login", response_model=Token)
async def login(
    payload: UserLogin,
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> Token:
    """Authenticate a verified user and return a bearer access token."""

    token = await auth_service.login(payload)
    return Token(access_token=token, token_type="bearer")


@router.get("/oauth/{provider}/start", response_model=OAuthStartResponse)
async def oauth_start(
    provider: str,
    redirect_uri: str | None = None,
    oauth_service: OAuthService = Depends(deps.get_oauth_service),
) -> OAuthStartResponse:
    """Return the provider authorization URL and state token for OAuth login."""

    provider_key = _normalize_provider(provider)
    auth_url, state = oauth_service.get_authorization_url(provider_key, redirect_uri=redirect_uri)
    return OAuthStartResponse(provider=provider_key, auth_url=auth_url, state=state)


@router.post("/oauth/{provider}/callback", response_model=OAuthToken)
async def oauth_callback(
    provider: str,
    payload: OAuthCallbackRequest,
    auth_service: AuthService = Depends(deps.get_auth_service),
    oauth_service: OAuthService = Depends(deps.get_oauth_service),
) -> OAuthToken:
    """Exchange the OAuth code for a profile and issue a bearer token."""

    provider_key = _normalize_provider(provider)
    profile = await oauth_service.exchange_code_for_profile(
        provider=provider_key, code=payload.code, state=payload.state, redirect_uri=payload.redirect_uri
    )
    token = await auth_service.login_with_oauth(profile)
    return OAuthToken(access_token=token, token_type="bearer", provider=provider_key)
