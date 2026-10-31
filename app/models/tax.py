from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class TaxRule(Base, TimestampMixin):
    """
    TaxRule represents an organization-specific tax rate (e.g. GST 18%, VAT 20%).
    Taxes are calculated automatically on quotation lines, subscription lines, and invoices.
    """
    __tablename__ = "tax_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )  # e.g. 18.00 for 18%
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="tax_rules")

    def calculate_tax(self, taxable_amount: Decimal) -> Decimal:
        """Calculates tax amount = taxable_amount * (rate / 100), rounded to 2 decimal places."""
        if not self.is_active or taxable_amount <= Decimal("0.00"):
            return Decimal("0.00")
        tax = taxable_amount * (self.rate / Decimal("100.00"))
        return round(tax, 2)

    def __repr__(self) -> str:
        return f"<TaxRule(id={self.id}, name='{self.name}', rate={self.rate}%)>"
