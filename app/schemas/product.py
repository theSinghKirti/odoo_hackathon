from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.product import ProductType


class ProductVariantBase(BaseModel):
    attribute_name: str = Field(..., max_length=100, description="Attribute name e.g. Brand, Tier")
    attribute_value: str = Field(..., max_length=100, description="Attribute value e.g. Odoo, Enterprise")
    price_extra: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Price surcharge added to base sales price")
    sku: Optional[str] = Field(None, max_length=100)
    is_active: bool = True


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantUpdate(BaseModel):
    attribute_name: Optional[str] = Field(None, max_length=100)
    attribute_value: Optional[str] = Field(None, max_length=100)
    price_extra: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    sku: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class ProductVariantResponse(ProductVariantBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    product_id: int
    effective_price: Decimal
    created_at: datetime
    updated_at: datetime


class ProductBase(BaseModel):
    name: str = Field(..., max_length=255, description="Product title or software package name")
    product_type: ProductType = Field(default=ProductType.SOFTWARE, description="software, service, addon, physical")
    sales_price: Decimal = Field(..., ge=Decimal("0.00"), description="Base unit sales price")
    cost_price: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Internal baseline cost")
    notes: Optional[str] = None
    is_active: bool = True


class ProductCreate(ProductBase):
    variants: Optional[List[ProductVariantCreate]] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    product_type: Optional[ProductType] = None
    sales_price: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    cost_price: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    created_at: datetime
    updated_at: datetime


class ProductDetailResponse(ProductResponse):
    variants: List[ProductVariantResponse] = []
