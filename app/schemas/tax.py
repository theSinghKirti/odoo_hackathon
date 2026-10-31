from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TaxRuleBase(BaseModel):
    name: str = Field(..., max_length=100, description="Tax rule label e.g. GST 18%, VAT 20%")
    rate: Decimal = Field(..., ge=Decimal("0.00"), le=Decimal("100.00"), description="Percentage tax rate e.g. 18.00")
    is_active: bool = Field(default=True, description="Active status for tax calculations")


class TaxRuleCreate(TaxRuleBase):
    pass


class TaxRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    rate: Optional[Decimal] = Field(None, ge=Decimal("0.00"), le=Decimal("100.00"))
    is_active: Optional[bool] = None


class TaxRuleResponse(TaxRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    created_at: datetime
    updated_at: datetime
