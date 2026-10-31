from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.invoice import InvoiceStatus
from app.schemas.customer import CustomerResponse
from app.schemas.product import ProductResponse, ProductVariantResponse


class InvoiceLineBase(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    description: Optional[str] = None
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    tax_id: Optional[int] = None
    discount_rule_id: Optional[int] = None
    is_addon: bool = False


class InvoiceLineCreate(InvoiceLineBase):
    pass


class InvoiceLineResponse(InvoiceLineBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    invoice_id: int
    tax_amount: Decimal
    discount_amount: Decimal
    line_total: Decimal
    product: Optional[ProductResponse] = None
    variant: Optional[ProductVariantResponse] = None
    created_at: datetime
    updated_at: datetime


class InvoiceCreate(BaseModel):
    customer_id: int
    subscription_id: Optional[int] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    lines: List[InvoiceLineCreate] = []


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    invoice_number: str
    subscription_id: Optional[int] = None
    customer_id: int
    invoice_date: date
    due_date: date
    payment_terms: Optional[str] = None
    status: InvoiceStatus
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    amount_due: Decimal
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    lines: List[InvoiceLineResponse] = []
    customer: Optional[CustomerResponse] = None


class InvoiceCancelRequest(BaseModel):
    reason: Optional[str] = None


class BillingSweepRequest(BaseModel):
    as_of_date: Optional[date] = None


class BillingSweepResponse(BaseModel):
    as_of_date: date
    subscriptions_evaluated: int
    invoices_generated: int
    total_billed_amount: Decimal
    invoice_ids: List[int]

