from decimal import Decimal
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product, ProductVariant, ProductType
from app.schemas.product import ProductCreate, ProductUpdate, ProductVariantCreate, ProductVariantUpdate


class ProductServiceError(Exception):
    """Base exception for product service errors."""
    pass


class ProductNotFoundError(ProductServiceError):
    """Raised when a requested product does not exist in the tenant organization."""
    pass


class ProductVariantNotFoundError(ProductServiceError):
    """Raised when a requested product variant does not exist."""
    pass


class DuplicateVariantError(ProductServiceError):
    """Raised when an attribute name and value already exist for the product."""
    pass


class ProductService:
    @staticmethod
    async def create_product(
        session: AsyncSession,
        organization_id: int,
        data: ProductCreate,
    ) -> Product:
        """
        Creates a new product for the given organization, optionally creating initial variants.
        """
        product = Product(
            organization_id=organization_id,
            name=data.name.strip(),
            product_type=data.product_type,
            sales_price=data.sales_price,
            cost_price=data.cost_price,
            notes=data.notes.strip() if data.notes else None,
            is_active=data.is_active,
        )
        session.add(product)
        await session.flush()

        if data.variants:
            for v_data in data.variants:
                variant = ProductVariant(
                    organization_id=organization_id,
                    product_id=product.id,
                    attribute_name=v_data.attribute_name.strip(),
                    attribute_value=v_data.attribute_value.strip(),
                    price_extra=v_data.price_extra,
                    sku=v_data.sku.strip() if v_data.sku else None,
                    is_active=v_data.is_active,
                )
                session.add(variant)

            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                raise DuplicateVariantError("Duplicate variant attribute detected on product creation.")

        await session.commit()
        await session.refresh(product)
        return await ProductService.get_product(session, organization_id=organization_id, product_id=product.id)

    @staticmethod
    async def get_product(
        session: AsyncSession,
        organization_id: int,
        product_id: int,
    ) -> Product:
        """
        Retrieves a product by ID scoped strictly to the organization.
        """
        stmt = (
            select(Product)
            .options(selectinload(Product.variants))
            .where(
                and_(
                    Product.id == product_id,
                    Product.organization_id == organization_id,
                )
            )
        )
        result = await session.execute(stmt)
        product = result.scalars().first()
        if not product:
            raise ProductNotFoundError(f"Product with id {product_id} not found in this organization.")
        return product

    @staticmethod
    async def list_products(
        session: AsyncSession,
        organization_id: int,
        product_type: Optional[ProductType] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Product]:
        """
        Lists products for an organization with optional filters and pagination.
        """
        filters = [Product.organization_id == organization_id]

        if product_type is not None:
            filters.append(Product.product_type == product_type)

        if is_active is not None:
            filters.append(Product.is_active == is_active)

        if search:
            search_clean = f"%{search.strip()}%"
            filters.append(Product.name.ilike(search_clean))

        stmt = (
            select(Product)
            .options(selectinload(Product.variants))
            .where(and_(*filters))
            .order_by(Product.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_product(
        session: AsyncSession,
        organization_id: int,
        product_id: int,
        data: ProductUpdate,
    ) -> Product:
        """
        Updates product attributes.
        """
        product = await ProductService.get_product(session, organization_id=organization_id, product_id=product_id)

        update_dict = data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(product, key, value)

        await session.commit()
        return await ProductService.get_product(session, organization_id=organization_id, product_id=product.id)

    @staticmethod
    async def add_variant(
        session: AsyncSession,
        organization_id: int,
        product_id: int,
        data: ProductVariantCreate,
    ) -> ProductVariant:
        """
        Adds a variant with a price surcharge to a product.
        """
        # Verify product exists in organization
        product = await ProductService.get_product(session, organization_id=organization_id, product_id=product_id)

        # Check for existing duplicate variant
        stmt = select(ProductVariant).where(
            and_(
                ProductVariant.product_id == product.id,
                ProductVariant.attribute_name == data.attribute_name.strip(),
                ProductVariant.attribute_value == data.attribute_value.strip(),
            )
        )
        res = await session.execute(stmt)
        if res.scalars().first():
            raise DuplicateVariantError(
                f"Variant with {data.attribute_name}='{data.attribute_value}' already exists on this product."
            )

        variant = ProductVariant(
            organization_id=organization_id,
            product_id=product.id,
            attribute_name=data.attribute_name.strip(),
            attribute_value=data.attribute_value.strip(),
            price_extra=data.price_extra,
            sku=data.sku.strip() if data.sku else None,
            is_active=data.is_active,
        )
        session.add(variant)
        try:
            await session.commit()
            return await ProductService.get_variant(session, organization_id=organization_id, variant_id=variant.id)
        except IntegrityError:
            await session.rollback()
            raise DuplicateVariantError("Duplicate variant attribute detected.")

    @staticmethod
    async def get_variant(
        session: AsyncSession,
        organization_id: int,
        variant_id: int,
    ) -> ProductVariant:
        """
        Retrieves a variant by ID scoped strictly to the organization.
        """
        stmt = (
            select(ProductVariant)
            .options(selectinload(ProductVariant.product))
            .where(
                and_(
                    ProductVariant.id == variant_id,
                    ProductVariant.organization_id == organization_id,
                )
            )
        )
        result = await session.execute(stmt)
        variant = result.scalars().first()
        if not variant:
            raise ProductVariantNotFoundError(f"Product variant with id {variant_id} not found in this organization.")
        return variant

    @staticmethod
    async def update_variant(
        session: AsyncSession,
        organization_id: int,
        variant_id: int,
        data: ProductVariantUpdate,
    ) -> ProductVariant:
        """
        Updates an existing variant's price_extra or metadata.
        """
        variant = await ProductService.get_variant(session, organization_id=organization_id, variant_id=variant_id)

        update_dict = data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(variant, key, value)

        try:
            await session.commit()
            return await ProductService.get_variant(session, organization_id=organization_id, variant_id=variant.id)
        except IntegrityError:
            await session.rollback()
            raise DuplicateVariantError("Updating variant resulted in duplicate attribute name/value.")

    @staticmethod
    def calculate_effective_price(
        product: Product,
        variant: Optional[ProductVariant] = None,
    ) -> Decimal:
        """
        Calculates total unit price:
        Base Product Sales Price + Variant Surcharge (price_extra).
        """
        base = product.sales_price
        surcharge = variant.price_extra if variant else Decimal("0.00")
        return base + surcharge
