from typing import List, TYPE_CHECKING
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.customer import Customer
    from app.models.product import Product
    from app.models.plan import SubscriptionPlan
    from app.models.tax import TaxRule
    from app.models.discount import DiscountRule
    from app.models.quotation_template import QuotationTemplate
    from app.models.quotation import Quotation
    from app.models.subscription import Subscription
    from app.models.invoice import Invoice


class Organization(Base, TimestampMixin):
    """
    Represents a tenant organization.
    Multi-tenancy boundary: all tenant resources belong to an organization.
    """
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    customers: Mapped[List["Customer"]] = relationship(
        "Customer",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    products: Mapped[List["Product"]] = relationship(
        "Product",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    plans: Mapped[List["SubscriptionPlan"]] = relationship(
        "SubscriptionPlan",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    tax_rules: Mapped[List["TaxRule"]] = relationship(
        "TaxRule",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    discount_rules: Mapped[List["DiscountRule"]] = relationship(
        "DiscountRule",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    quotation_templates: Mapped[List["QuotationTemplate"]] = relationship(
        "QuotationTemplate",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    quotations: Mapped[List["Quotation"]] = relationship(
        "Quotation",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}', slug='{self.slug}')>"

