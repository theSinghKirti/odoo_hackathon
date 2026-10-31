from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, require_admin, require_staff_or_admin
from app.db.session import get_async_db
from app.models.organization import Organization
from app.models.product import ProductType
from app.models.user import User
from app.schemas.product import (
    ProductCreate,
    ProductDetailResponse,
    ProductResponse,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantResponse,
    ProductVariantUpdate,
)
from app.services.product_service import (
    DuplicateVariantError,
    ProductNotFoundError,
    ProductService,
    ProductVariantNotFoundError,
)

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=List[ProductDetailResponse])
async def list_products(
    product_type: Optional[ProductType] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List products within the current tenant organization.
    Supports filtering by product_type, active status, search term, and pagination.
    Accessible to Staff and Admin roles.
    """
    return await ProductService.list_products(
        session=db,
        organization_id=current_org.id,
        product_type=product_type,
        is_active=is_active,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=ProductDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create a new product with optional initial variants.
    Restricted strictly to Admin role.
    """
    try:
        return await ProductService.create_product(
            session=db,
            organization_id=current_org.id,
            data=data,
        )
    except DuplicateVariantError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/{product_id}", response_model=ProductDetailResponse)
async def get_product(
    product_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Retrieve product details along with its configured variants.
    Accessible to Staff and Admin roles.
    """
    try:
        return await ProductService.get_product(
            session=db,
            organization_id=current_org.id,
            product_id=product_id,
        )
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{product_id}", response_model=ProductDetailResponse)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update product fields (name, price, notes, active status).
    Restricted strictly to Admin role.
    """
    try:
        return await ProductService.update_product(
            session=db,
            organization_id=current_org.id,
            product_id=product_id,
            data=data,
        )
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{product_id}/variants", response_model=ProductVariantResponse, status_code=status.HTTP_201_CREATED)
async def add_product_variant(
    product_id: int,
    data: ProductVariantCreate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Add a variant to a product with a price surcharge (price_extra).
    E.g. Choosing Brand = Odoo adds +560.00 to price.
    Restricted strictly to Admin role.
    """
    try:
        return await ProductService.add_variant(
            session=db,
            organization_id=current_org.id,
            product_id=product_id,
            data=data,
        )
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DuplicateVariantError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/{product_id}/variants/{variant_id}", response_model=ProductVariantResponse)
async def update_product_variant(
    product_id: int,
    variant_id: int,
    data: ProductVariantUpdate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update a variant's attributes or surcharge price_extra.
    Restricted strictly to Admin role.
    """
    try:
        variant = await ProductService.get_variant(
            session=db,
            organization_id=current_org.id,
            variant_id=variant_id,
        )
        if variant.product_id != product_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Variant {variant_id} does not belong to product {product_id}.",
            )
        return await ProductService.update_variant(
            session=db,
            organization_id=current_org.id,
            variant_id=variant_id,
            data=data,
        )
    except ProductVariantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DuplicateVariantError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
