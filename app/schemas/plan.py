from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.plan import BillingInterval


class PlanBase(BaseModel):
    name: str = Field(..., max_length=255, description="Subscription plan name e.g. Monthly Starter, Enterprise Annual")
    description: Optional[str] = Field(None, description="Plan description and features overview")
    billing_interval: BillingInterval = Field(..., description="daily, weekly, monthly, or yearly")
    interval_count: int = Field(default=1, ge=1, description="Interval count multiplier (e.g. 1 = every month, 3 = quarterly)")
    base_price: Decimal = Field(..., ge=Decimal("0.00"), description="Recurring price per billing cycle")
    currency: str = Field(default="INR", min_length=3, max_length=3, description="ISO-4217 currency code")
    min_quantity: int = Field(default=1, ge=1, description="Minimum seats or license quantity required")
    available_from: Optional[date] = Field(None, description="Start date from which the plan can be offered")
    available_until: Optional[date] = Field(None, description="End date after which the plan cannot be offered")

    # Lifecycle policy flags
    auto_close_on_expiry: bool = Field(default=True, description="Whether subscriptions close automatically upon reaching expiry date")
    allow_early_close: bool = Field(default=True, description="Whether early termination before cycle end is permitted")
    allow_pause: bool = Field(default=True, description="Whether subscriptions can be temporarily paused and resumed")
    allow_renewal: bool = Field(default=True, description="Whether the plan can be renewed for subsequent terms")

    is_active: bool = Field(default=True, description="Active status for catalog availability")


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    billing_interval: Optional[BillingInterval] = None
    interval_count: Optional[int] = Field(None, ge=1)
    base_price: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    min_quantity: Optional[int] = Field(None, ge=1)
    available_from: Optional[date] = None
    available_until: Optional[date] = None
    auto_close_on_expiry: Optional[bool] = None
    allow_early_close: Optional[bool] = None
    allow_pause: Optional[bool] = None
    allow_renewal: Optional[bool] = None
    is_active: Optional[bool] = None


class PlanResponse(PlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    is_available_today: bool = True
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_with_availability(cls, plan) -> "PlanResponse":
        res = cls.model_validate(plan)
        res.is_available_today = plan.is_available()
        return res
