"""OAuth2 helpers for Google and GitHub login/registration flows."""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

OAuthProvider = Literal["google", "github"]


@dataclass
class OAuthProfile:
    """Normalized profile data returned by OAuth providers."""

    provider: OAuthProvider
    provider_id: str
    email: Optional[str]
    name: Optional[str] = None


class OAuthService:
    """Build authorization URLs, validate state, and exchange codes for profiles."""

    def __init__(self) -> None:
        self.state_ttl = settings.OAUTH_STATE_TTL_SECONDS

    # -----------------------
    # State helpers
    # -----------------------
    def _sign_state(self, nonce: str, ts: int) -> str:
        payload = f"{nonce}:{ts}"
        sig = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}:{sig}"

    def generate_state(self) -> str:
        """Create an HMAC-signed state token to mitigate CSRF in OAuth redirects."""
        nonce = secrets.token_urlsafe(16)
        ts = int(time.time())
        return self._sign_state(nonce, ts)

    def validate_state(self, state: str) -> None:
        """Validate signature and TTL of the provided state token."""
        try:
            nonce, ts_str, sig = state.split(":")
            ts = int(ts_str)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state.")

        expected = self._sign_state(nonce, ts)
        if not hmac.compare_digest(expected, state):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state signature.")

        if time.time() - ts > self.state_ttl:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state has expired.")

    # -----------------------
    # Public API
    # -----------------------
    def get_authorization_url(self, provider: OAuthProvider, redirect_uri: str | None = None) -> tuple[str, str]:
        """Return an authorization URL and state token for the given provider."""

        state = self.generate_state()

        if provider == "google":
            client_id = settings.GOOGLE_CLIENT_ID
            redirect = redirect_uri or settings.GOOGLE_REDIRECT_URI
            if not all([client_id, settings.GOOGLE_CLIENT_SECRET, redirect]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI.",
                )
            params = {
                "client_id": client_id,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": "openid email profile",
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
            url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
            return url, state

        if provider == "github":
            client_id = settings.GITHUB_CLIENT_ID
            redirect = redirect_uri or settings.GITHUB_REDIRECT_URI
            if not all([client_id, settings.GITHUB_CLIENT_SECRET, redirect]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="GitHub OAuth is not configured. Set GITHUB_CLIENT_ID/SECRET/REDIRECT_URI.",
                )
            params = {
                "client_id": client_id,
                "redirect_uri": redirect,
                "scope": "read:user user:email",
                "state": state,
                "allow_signup": "true",
            }
            url = "https://github.com/login/oauth/authorize?" + urlencode(params)
            return url, state

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported OAuth provider.")

    async def exchange_code_for_profile(
        self, provider: OAuthProvider, code: str, state: str, redirect_uri: str | None = None
    ) -> OAuthProfile:
        """Verify state and exchange an authorization code for a normalized profile."""

        self.validate_state(state)

        if provider == "google":
            return await self._exchange_google(code, redirect_uri or settings.GOOGLE_REDIRECT_URI)
        if provider == "github":
            return await self._exchange_github(code, redirect_uri or settings.GITHUB_REDIRECT_URI)

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported OAuth provider.")

    # -----------------------
    # Provider implementations
    # -----------------------
    async def _exchange_google(self, code: str, redirect_uri: str | None) -> OAuthProfile:
        if not all([settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET, redirect_uri]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI.",
            )

        token_payload = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=20) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_resp.status_code != 200:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to exchange Google code.")
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google token missing access token.")

            user_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to fetch Google profile.")
            user_data = user_resp.json()

        provider_id = user_data.get("sub")
        email = user_data.get("email")
        name = user_data.get("name")
        if not provider_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google profile missing id.")

        return OAuthProfile(provider="google", provider_id=str(provider_id), email=email, name=name)

    async def _exchange_github(self, code: str, redirect_uri: str | None) -> OAuthProfile:
        if not all([settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET, redirect_uri]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub OAuth is not configured. Set GITHUB_CLIENT_ID/SECRET/REDIRECT_URI.",
            )

        token_payload = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data=token_payload,
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to exchange GitHub code.")
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub token missing access token.")

            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            if user_resp.status_code != 200:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to fetch GitHub profile.")
            user_data = user_resp.json()

            email = user_data.get("email")
            # GitHub may omit public email; fetch primary verified email if missing
            if not email:
                emails_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
                )
                if emails_resp.status_code == 200:
                    for entry in emails_resp.json():
                        if entry.get("primary") and entry.get("verified") and entry.get("email"):
                            email = entry["email"]
                            break

        provider_id = user_data.get("id")
        name = user_data.get("name") or user_data.get("login")
        if not provider_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub profile missing id.")

        return OAuthProfile(provider="github", provider_id=str(provider_id), email=email, name=name)
