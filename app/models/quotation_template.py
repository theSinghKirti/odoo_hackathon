from typing import List, Optional, TYPE_CHECKING
from decimal import Decimal
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.plan import SubscriptionPlan
    from app.models.product import Product, ProductVariant


class QuotationTemplate(Base, TimestampMixin):
    """
    Standardized quotation template created by Admin/Staff.
    Pre-configures default subscription plan, product lines, and validity duration.
    """
    __tablename__ = "quotation_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    validity_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="quotation_templates")
    plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan", lazy="joined")
    lines: Mapped[List["QuotationTemplateLine"]] = relationship(
        "QuotationTemplateLine",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="QuotationTemplateLine.id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<QuotationTemplate(id={self.id}, name='{self.name}', validity_days={self.validity_days})>"


class QuotationTemplateLine(Base, TimestampMixin):
    """
    Pre-configured product line in a quotation template.
    """
    __tablename__ = "quotation_template_lines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("quotation_templates.id", ondelete="CASCADE"),
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

    # Relationships
    template: Mapped["QuotationTemplate"] = relationship("QuotationTemplate", back_populates="lines")
    product: Mapped["Product"] = relationship("Product", lazy="joined")
    variant: Mapped[Optional["ProductVariant"]] = relationship("ProductVariant", lazy="joined")

    def __repr__(self) -> str:
        return f"<QuotationTemplateLine(id={self.id}, product_id={self.product_id}, qty={self.quantity})>"
