from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentCreate(BaseModel):
    payment_method: PaymentMethod = Field(..., description="Payment method: bank_transfer, cheque, cash, razorpay, other")
    amount: Decimal = Field(..., gt=Decimal("0.00"), description="Positive payment amount")
    payment_date: Optional[date] = Field(default=None, description="Date payment received/realized")
    note: Optional[str] = Field(default=None, max_length=500, description="Reference note (UTR, cheque number, etc.)")


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    invoice_id: int
    customer_id: int
    payment_method: PaymentMethod
    amount: Decimal
    payment_date: date
    note: Optional[str] = None
    status: PaymentStatus
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    created_at: datetime


class RazorpayOrderResponse(BaseModel):
    order_id: str
    amount: int  # Amount in paise (integer)
    currency: str = "INR"
    key_id: str
    invoice_id: int
    invoice_number: str
    customer_name: str
    customer_email: str


class RazorpayVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class RazorpayVerifyResponse(BaseModel):
    status: str
    message: str
    payment_id: int
    invoice_id: int
    amount_paid: Decimal
    amount_due: Decimal
    invoice_status: str

