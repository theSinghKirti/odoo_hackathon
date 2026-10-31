from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    full_name: str
    email: EmailStr
    role: str
    is_active: bool = True
    is_verified: bool = False


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str = "customer"


class StaffCreate(BaseModel):
    """Admin-only payload to create a Staff account."""
    full_name: str
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

