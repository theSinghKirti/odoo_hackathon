from datetime import datetime
from pydantic import BaseModel, ConfigDict


class OrganizationBase(BaseModel):
    name: str
    slug: str
    is_active: bool = True


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

