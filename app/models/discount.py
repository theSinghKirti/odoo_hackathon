from datetime import date
from decimal import Decimal
import enum
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.product import Product


class DiscountType(str, enum.Enum):
    FIXED_AMOUNT = "fixed_amount"
    PERCENTAGE = "percentage"


class DiscountScope(str, enum.Enum):
    PRODUCT = "product"
    SUBSCRIPTION = "subscription"


class DiscountRule(Base, TimestampMixin):
    """
    DiscountRule created by Admin:
    - Fixed amount or percentage discount.
    - Minimum purchase amount or minimum quantity triggers.
    - Start date and end date availability.
    - Maximum usage ceiling (max_uses) tracking times_used.
    - Applicable to specific products or whole subscriptions.
    - Automatically applied on invoices and stops when expired or exhausted.
    """
    __tablename__ = "discount_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(DiscountType, name="discount_type_enum", native_enum=False),
        nullable=False,
    )
    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    min_purchase_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    min_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    scope: Mapped[DiscountScope] = mapped_column(
        Enum(DiscountScope, name="discount_scope_enum", native_enum=False),
        default=DiscountScope.SUBSCRIPTION,
        nullable=False,
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="discount_rules")
    product: Mapped[Optional["Product"]] = relationship("Product", lazy="joined")

    def is_eligible(
        self,
        amount: Decimal,
        quantity: int = 1,
        target_date: Optional[date] = None,
        target_product_id: Optional[int] = None,
    ) -> bool:
        """
        Evaluates whether a quote/subscription/invoice line qualifies for this discount rule.
        """
        if not self.is_active:
            return False

        # Usage limit check
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return False

        # Date window check
        d = target_date or date.today()
        if self.start_date and d < self.start_date:
            return False
        if self.end_date and d > self.end_date:
            return False

        # Minimum quantity check
        if self.min_quantity is not None and quantity < self.min_quantity:
            return False

        # Minimum purchase amount check
        if self.min_purchase_amount is not None and amount < self.min_purchase_amount:
            return False

        # Product scope check
        if self.scope == DiscountScope.PRODUCT:
            if target_product_id is None or self.product_id != target_product_id:
                return False

        return True

    def calculate_discount(self, base_amount: Decimal) -> Decimal:
        """
        Computes the discount amount based on fixed amount or percentage.
        Cannot exceed base_amount (discounted amount cannot go below zero).
        """
        if base_amount <= Decimal("0.00"):
            return Decimal("0.00")

        if self.discount_type == DiscountType.FIXED_AMOUNT:
            discount = min(self.discount_value, base_amount)
        elif self.discount_type == DiscountType.PERCENTAGE:
            pct = min(self.discount_value, Decimal("100.00"))
            discount = base_amount * (pct / Decimal("100.00"))
        else:
            discount = Decimal("0.00")

        return round(discount, 2)

    def __repr__(self) -> str:
        return f"<DiscountRule(id={self.id}, name='{self.name}', type={self.discount_type}, value={self.discount_value})>"
