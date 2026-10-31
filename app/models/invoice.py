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
    from app.models.organization import Organization
    from app.models.product import Product, ProductVariant
    from app.models.subscription import Subscription
    from app.models.tax import TaxRule


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PAID = "paid"
    CANCELLED = "cancelled"


class Invoice(Base, TimestampMixin):
    """
    Invoice generated automatically on billing days or created by staff.
    Follows lifecycle: Draft -> Confirmed -> Paid (or Cancelled).
    """
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_number", name="uq_invoices_org_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status_enum", native_enum=False),
        default=InvoiceStatus.DRAFT,
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
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    amount_due: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    @property
    def issue_date(self) -> date:
        return self.invoice_date

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="invoices")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="invoices", lazy="joined")
    subscription: Mapped[Optional["Subscription"]] = relationship("Subscription", back_populates="invoices", lazy="joined")
    lines: Mapped[List["InvoiceLine"]] = relationship(
        "InvoiceLine",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLine.id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Invoice(id={self.id}, number='{self.invoice_number}', status='{self.status}', due={self.amount_due})>"


class InvoiceLine(Base, TimestampMixin):
    """
    Line item inside an invoice.
    """
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"),
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
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
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
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="lines")
    product: Mapped["Product"] = relationship("Product", lazy="joined")
    variant: Mapped[Optional["ProductVariant"]] = relationship("ProductVariant", lazy="joined")
    tax_rule: Mapped[Optional["TaxRule"]] = relationship("TaxRule", lazy="joined")
    discount_rule: Mapped[Optional["DiscountRule"]] = relationship("DiscountRule", lazy="joined")

    def __repr__(self) -> str:
        return f"<InvoiceLine(id={self.id}, product_id={self.product_id}, qty={self.quantity}, total={self.line_total})>"
