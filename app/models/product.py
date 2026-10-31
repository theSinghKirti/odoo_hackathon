import enum
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class ProductType(str, enum.Enum):
    SOFTWARE = "software"
    SERVICE = "service"
    ADDON = "addon"
    PHYSICAL = "physical"


class Product(Base, TimestampMixin):
    """
    Product entity representing a catalog offering (software, service, add-on, or physical good).
    Belongs strictly to an Organization (multi-tenant boundary).
    """
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType, name="product_type_enum", native_enum=False),
        default=ProductType.SOFTWARE,
        nullable=False,
        index=True,
    )
    sales_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    cost_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="products")
    variants: Mapped[List["ProductVariant"]] = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVariant.id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', type='{self.product_type}', sales_price={self.sales_price})>"


class ProductVariant(Base, TimestampMixin):
    """
    ProductVariant represents a dimensional option of a product (e.g. Brand, Tier, Region).
    Each variant can define a price surcharge ('price_extra') that adds to the product's sales_price.
    Example: Choosing Brand = Odoo adds +560.00 to base price.
    """
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "attribute_name", "attribute_value", name="uq_product_variants_attr"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attribute_name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Brand", "Edition"
    attribute_value: Mapped[str] = mapped_column(String(100), nullable=False) # e.g. "Odoo", "Enterprise"
    price_extra: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )  # e.g. 560.00
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="variants", lazy="joined")

    @property
    def effective_price(self) -> Decimal:
        """Calculates effective sales price = base sales price + variant price_extra."""
        base = self.product.sales_price if self.product else Decimal("0.00")
        return base + self.price_extra

    def __repr__(self) -> str:
        return f"<ProductVariant(id={self.id}, attr='{self.attribute_name}:{self.attribute_value}', extra={self.price_extra})>"
