from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class CustomerCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    user_id: Optional[int] = None
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

