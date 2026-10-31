from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.quotation import QuotationStatus
from app.schemas.customer import CustomerResponse
from app.schemas.plan import PlanResponse
from app.schemas.product import ProductResponse, ProductVariantResponse


class QuotationLineBase(BaseModel):
    product_id: int = Field(..., description="ID of product")
    variant_id: Optional[int] = Field(None, description="Optional ID of variant (e.g. +560 brand surcharge)")
    quantity: int = Field(default=1, ge=1, description="Quantity")
    unit_price: Optional[Decimal] = Field(None, ge=Decimal("0.00"), description="Unit price; computed if not specified")
    tax_id: Optional[int] = Field(None, description="Optional tax rule ID")
    discount_rule_id: Optional[int] = Field(None, description="Optional discount rule ID")


class QuotationLineCreate(QuotationLineBase):
    pass


class QuotationLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    quotation_id: int
    product_id: int
    variant_id: Optional[int] = None
    quantity: int
    unit_price: Decimal
    tax_id: Optional[int] = None
    discount_rule_id: Optional[int] = None
    tax_amount: Decimal
    discount_amount: Decimal
    line_total: Decimal
    product: Optional[ProductResponse] = None
    variant: Optional[ProductVariantResponse] = None
    created_at: datetime
    updated_at: datetime


class QuotationBase(BaseModel):
    customer_id: int = Field(..., description="Target customer ID")
    plan_id: Optional[int] = Field(None, description="Subscription plan ID (optional if template_id is used)")
    template_id: Optional[int] = Field(None, description="Optional quotation template ID to pre-populate lines and terms")
    start_date: Optional[date] = Field(None, description="Contract start date; defaults to today")
    expiry_date: Optional[date] = Field(None, description="Quotation expiration date; defaults to start_date + validity_days")
    payment_terms: Optional[str] = Field(None, max_length=255, description="e.g. 'Immediate Payment', 'Net 15', 'Net 30'")
    notes: Optional[str] = Field(None, description="Customer-facing or internal remarks")


class QuotationCreate(QuotationBase):
    lines: Optional[List[QuotationLineCreate]] = Field(None, description="Line items; if omitted and template_id is present, template lines are copied")


class QuotationUpdate(BaseModel):
    plan_id: Optional[int] = None
    start_date: Optional[date] = None
    expiry_date: Optional[date] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[QuotationStatus] = None
    lines: Optional[List[QuotationLineCreate]] = None


class QuotationStatusUpdate(BaseModel):
    status: QuotationStatus = Field(..., description="Target quotation status transition")


class QuotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    quotation_number: str
    customer_id: int
    plan_id: int
    template_id: Optional[int] = None
    start_date: date
    expiry_date: date
    payment_terms: Optional[str] = None
    status: QuotationStatus
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    notes: Optional[str] = None
    customer: Optional[CustomerResponse] = None
    plan: Optional[PlanResponse] = None
    lines: List[QuotationLineResponse] = []
    created_at: datetime
    updated_at: datetime
