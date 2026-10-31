from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.organization import Organization
    from app.models.payment import Payment
    from app.models.user import User


class Customer(Base, TimestampMixin):
    """
    Customer entity representing a client of a specific organization.
    A Customer may optionally be linked to a User account (self-service portal).
    """
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_customers_organization_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="customers")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="customer_profile")
    invoices: Mapped[List["Invoice"]] = relationship("Invoice", back_populates="customer", lazy="selectin")
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="customer", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, name='{self.name}', org_id={self.organization_id})>"
