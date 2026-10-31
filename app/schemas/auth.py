from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    organization_slug: Optional[str] = Field(
        None,
        description="Tenant slug. If omitted, defaults to the reference tenant.",
    )
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=9)


class RegisterAdminRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=255)
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=9)
    organization_slug: Optional[str] = Field(
        None,
        description="Custom tenant slug. If omitted, derived from organization name.",
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=9)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None
    dev_token: Optional[str] = None  # Populated only in dev when simulation enabled
