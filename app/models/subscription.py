from datetime import date
from decimal import Decimal
import enum
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.discount import DiscountRule
    from app.models.invoice import Invoice
    from app.models.organization import Organization
    from app.models.plan import SubscriptionPlan
    from app.models.product import Product, ProductVariant
    from app.models.quotation import Quotation
    from app.models.tax import TaxRule


class SubscriptionStatus(str, enum.Enum):
    DRAFT = "draft"
    QUOTATION = "quotation"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class Subscription(Base, TimestampMixin):
    """
    Core recurring subscription contract.
    Governed by plan lifecycle rules and generates automated invoices on billing days.
    """
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("organization_id", "subscription_number", name="uq_subscriptions_org_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quotation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("quotations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_billing_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    last_billed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status_enum", native_enum=False),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # Policy snapshot copied from plan at activation time
    auto_close_on_expiry: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_early_close: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_pause: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_renewal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Recurring billing totals
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="subscriptions")
    customer: Mapped["Customer"] = relationship("Customer", lazy="joined")
    plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan", lazy="joined")
    quotation: Mapped[Optional["Quotation"]] = relationship("Quotation", back_populates="subscription", lazy="joined")
    lines: Mapped[List["SubscriptionLine"]] = relationship(
        "SubscriptionLine",
        back_populates="subscription",
        cascade="all, delete-orphan",
        order_by="SubscriptionLine.id",
        lazy="selectin",
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice",
        back_populates="subscription",
        order_by="Invoice.id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, number='{self.subscription_number}', status='{self.status}')>"


class SubscriptionLine(Base, TimestampMixin):
    """
    Recurring service/product line belonging to an active subscription.
    """
    __tablename__ = "subscription_lines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    variant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    tax_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tax_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    discount_rule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("discount_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    line_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    is_addon: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="lines")
    product: Mapped["Product"] = relationship("Product", lazy="joined")
    variant: Mapped[Optional["ProductVariant"]] = relationship("ProductVariant", lazy="joined")
    tax_rule: Mapped[Optional["TaxRule"]] = relationship("TaxRule", lazy="joined")
    discount_rule: Mapped[Optional["DiscountRule"]] = relationship("DiscountRule", lazy="joined")

    def __repr__(self) -> str:
        return f"<SubscriptionLine(id={self.id}, product_id={self.product_id}, qty={self.quantity}, total={self.line_total})>"
