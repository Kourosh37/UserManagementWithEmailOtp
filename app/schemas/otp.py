"""Pydantic schemas for OTP verification and resend flows."""

from pydantic import BaseModel, EmailStr


class OTPVerify(BaseModel):
    """Payload used when submitting a received OTP code for validation."""

    email: EmailStr
    code: str


class OTPRequest(BaseModel):
    """Payload used to request a new OTP for a specific email."""

    email: EmailStr
