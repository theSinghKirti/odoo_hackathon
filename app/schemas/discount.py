from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.discount import DiscountScope, DiscountType


class DiscountRuleBase(BaseModel):
    name: str = Field(..., max_length=255, description="Discount promo name e.g. Volume Deal 15% Off, New Year 500 Flat")
    discount_type: DiscountType = Field(..., description="fixed_amount or percentage")
    discount_value: Decimal = Field(..., ge=Decimal("0.00"), description="Fixed amount or percentage value")
    min_purchase_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Minimum spend trigger")
    min_quantity: int = Field(default=1, ge=1, description="Minimum quantity trigger")
    start_date: Optional[date] = Field(None, description="Start date of discount promo")
    end_date: Optional[date] = Field(None, description="Expiration date of discount promo")
    max_uses: Optional[int] = Field(None, ge=1, description="Maximum total uses allowed before rule auto-depletes")
    scope: DiscountScope = Field(default=DiscountScope.SUBSCRIPTION, description="product or subscription")
    product_id: Optional[int] = Field(None, description="Required when scope is product")
    is_active: bool = Field(default=True, description="Active status")


class DiscountRuleCreate(DiscountRuleBase):
    pass


class DiscountRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    min_purchase_amount: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    min_quantity: Optional[int] = Field(None, ge=1)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    max_uses: Optional[int] = Field(None, ge=1)
    scope: Optional[DiscountScope] = None
    product_id: Optional[int] = None
    is_active: Optional[bool] = None


class DiscountRuleResponse(DiscountRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    times_used: int
    created_at: datetime
    updated_at: datetime
