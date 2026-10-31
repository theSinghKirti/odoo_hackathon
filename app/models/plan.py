from datetime import date
from decimal import Decimal
import enum
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class BillingInterval(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionPlan(Base, TimestampMixin):
    """
    SubscriptionPlan entity defining recurring pricing, billing interval,
    minimum seat/quantity requirements, availability date windows, and lifecycle rules.
    Belongs strictly to an Organization (multi-tenant boundary).
    """
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Billing cycle parameters
    billing_interval: Mapped[BillingInterval] = mapped_column(
        Enum(BillingInterval, name="billing_interval_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    interval_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    base_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Availability date window
    available_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    available_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Lifecycle policy flags (Admin configured plan-by-plan according to problem statement)
    auto_close_on_expiry: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_early_close: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_pause: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_renewal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="plans")

    def is_available(self, target_date: Optional[date] = None) -> bool:
        """Checks if the plan is within its configured availability window."""
        if not self.is_active:
            return False
        d = target_date or date.today()
        if self.available_from and d < self.available_from:
            return False
        if self.available_until and d > self.available_until:
            return False
        return True

    def __repr__(self) -> str:
        return f"<SubscriptionPlan(id={self.id}, name='{self.name}', interval='{self.billing_interval}', price={self.base_price})>"
