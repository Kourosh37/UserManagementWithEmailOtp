from pydantic import BaseModel, EmailStr


class OTPVerify(BaseModel):
    email: EmailStr
    code: str


class OTPRequest(BaseModel):
    email: EmailStr
