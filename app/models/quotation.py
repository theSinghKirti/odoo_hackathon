from datetime import date
from decimal import Decimal
import enum
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.discount import DiscountRule
    from app.models.organization import Organization
    from app.models.plan import SubscriptionPlan
    from app.models.product import Product, ProductVariant
    from app.models.quotation_template import QuotationTemplate
    from app.models.subscription import Subscription
    from app.models.tax import TaxRule


class QuotationStatus(str, enum.Enum):
    DRAFT = "draft"
    QUOTATION = "quotation"
    CONFIRMED = "confirmed"
    CONVERTED = "converted"
    CANCELLED = "cancelled"


class Quotation(Base, TimestampMixin):
    """
    Quotation prepared for a customer.
    Follows lifecycle: Draft -> Quotation -> Confirmed -> Converted (or Cancelled).
    """
    __tablename__ = "quotations"
    __table_args__ = (
        UniqueConstraint("organization_id", "quotation_number", name="uq_quotations_org_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quotation_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
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
    template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("quotation_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[QuotationStatus] = mapped_column(
        Enum(QuotationStatus, name="quotation_status_enum", native_enum=False),
        default=QuotationStatus.DRAFT,
        nullable=False,
        index=True,
    )

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
    organization: Mapped["Organization"] = relationship("Organization", back_populates="quotations")
    customer: Mapped["Customer"] = relationship("Customer", lazy="joined")
    plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan", lazy="joined")
    template: Mapped[Optional["QuotationTemplate"]] = relationship("QuotationTemplate", lazy="joined")
    lines: Mapped[List["QuotationLine"]] = relationship(
        "QuotationLine",
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="QuotationLine.id",
        lazy="selectin",
    )
    subscription: Mapped[Optional["Subscription"]] = relationship(
        "Subscription",
        back_populates="quotation",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<Quotation(id={self.id}, number='{self.quotation_number}', status='{self.status}')>"


class QuotationLine(Base, TimestampMixin):
    """
    Line item inside a quotation with product, variant, quantity, tax, and discount breakdown.
    """
    __tablename__ = "quotation_lines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("quotations.id", ondelete="CASCADE"),
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

    # Relationships
    quotation: Mapped["Quotation"] = relationship("Quotation", back_populates="lines")
    product: Mapped["Product"] = relationship("Product", lazy="joined")
    variant: Mapped[Optional["ProductVariant"]] = relationship("ProductVariant", lazy="joined")
    tax_rule: Mapped[Optional["TaxRule"]] = relationship("TaxRule", lazy="joined")
    discount_rule: Mapped[Optional["DiscountRule"]] = relationship("DiscountRule", lazy="joined")

    def __repr__(self) -> str:
        return f"<QuotationLine(id={self.id}, product_id={self.product_id}, qty={self.quantity}, total={self.line_total})>"
