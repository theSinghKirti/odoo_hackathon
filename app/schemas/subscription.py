from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

from app.models.subscription import SubscriptionStatus
from app.schemas.customer import CustomerResponse
from app.schemas.plan import PlanResponse
from app.schemas.product import ProductResponse, ProductVariantResponse


class SubscriptionLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    subscription_id: int
    product_id: int
    variant_id: Optional[int] = None
    quantity: int
    unit_price: Decimal
    tax_id: Optional[int] = None
    discount_rule_id: Optional[int] = None
    tax_amount: Decimal
    discount_amount: Decimal
    line_total: Decimal
    is_addon: bool
    product: Optional[ProductResponse] = None
    variant: Optional[ProductVariantResponse] = None
    created_at: datetime
    updated_at: datetime


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    subscription_number: str
    customer_id: int
    plan_id: int
    quotation_id: Optional[int] = None
    start_date: date
    expiry_date: date
    next_billing_date: date
    last_billed_date: Optional[date] = None
    payment_terms: Optional[str] = None
    status: SubscriptionStatus
    auto_close_on_expiry: bool
    allow_early_close: bool
    allow_pause: bool
    allow_renewal: bool
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    notes: Optional[str] = None
    customer: Optional[CustomerResponse] = None
    plan: Optional[PlanResponse] = None
    lines: List[SubscriptionLineResponse] = []
    created_at: datetime
    updated_at: datetime
