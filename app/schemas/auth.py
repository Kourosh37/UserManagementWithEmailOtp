"""Pydantic schemas for authentication-related payloads and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Literal


class UserBase(BaseModel):
    """Base fields shared across user-related schemas."""

    email: EmailStr


class UserCreate(UserBase):
    """Payload for registration requests."""

    password: str


class UserLogin(UserBase):
    """Payload for login attempts."""

    password: str


class UserResponse(UserBase):
    """Response body representing a user record."""

    id: int
    is_active: bool
    is_verified: bool
    created_at: datetime
    auth_provider: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """Bearer token response returned after successful authentication."""

    access_token: str
    token_type: str = "bearer"


class OAuthStartResponse(BaseModel):
    """Authorization URL and state for initiating an OAuth login/registration."""

    provider: Literal["google", "github"]
    auth_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """Payload sent from the frontend after provider redirects with a code."""

    code: str
    state: str
    redirect_uri: str | None = None


class OAuthToken(Token):
    """Bearer token augmented with the provider used to issue it."""

    provider: Literal["google", "github"]


class AdminUserCreate(BaseModel):
    """Payload for admin-driven user creation."""

    email: EmailStr
    password: str | None = None
    is_active: bool = True
    is_verified: bool = True


class AdminUserUpdate(BaseModel):
    """Payload for admin-driven user updates (all optional)."""

    email: EmailStr | None = None
    password: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
