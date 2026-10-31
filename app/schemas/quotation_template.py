from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.product import ProductResponse, ProductVariantResponse


class QuotationTemplateLineBase(BaseModel):
    product_id: int = Field(..., description="ID of catalog product")
    variant_id: Optional[int] = Field(None, description="Optional ID of product variant")
    quantity: int = Field(default=1, ge=1, description="Quantity")
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Unit price")


class QuotationTemplateLineCreate(QuotationTemplateLineBase):
    pass


class QuotationTemplateLineResponse(QuotationTemplateLineBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    template_id: int
    product: Optional[ProductResponse] = None
    variant: Optional[ProductVariantResponse] = None
    created_at: datetime
    updated_at: datetime


class QuotationTemplateBase(BaseModel):
    name: str = Field(..., max_length=255, description="Template label e.g. 'Standard SaaS Starter'")
    validity_days: int = Field(default=30, ge=1, le=365, description="Validity duration in days")
    plan_id: int = Field(..., description="Default subscription plan ID")
    notes: Optional[str] = Field(None, description="Standard notes/terms for this template")


class QuotationTemplateCreate(QuotationTemplateBase):
    lines: List[QuotationTemplateLineCreate] = Field(default=[], description="Pre-configured template lines")


class QuotationTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    validity_days: Optional[int] = Field(None, ge=1, le=365)
    plan_id: Optional[int] = None
    notes: Optional[str] = None
    lines: Optional[List[QuotationTemplateLineCreate]] = None


class QuotationTemplateResponse(QuotationTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    lines: List[QuotationTemplateLineResponse] = []
    created_at: datetime
    updated_at: datetime
