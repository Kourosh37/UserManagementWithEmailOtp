"""Pydantic schemas for authentication-related payloads and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


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

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """Bearer token response returned after successful authentication."""

    access_token: str
    token_type: str = "bearer"
