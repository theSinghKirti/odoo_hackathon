from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, require_admin, require_staff_or_admin
from app.db.session import get_async_db
from app.models.discount import DiscountScope
from app.models.organization import Organization
from app.models.user import User
from app.schemas.discount import DiscountRuleCreate, DiscountRuleResponse, DiscountRuleUpdate
from app.services.discount_service import DiscountRuleNotFoundError, DiscountService

router = APIRouter(prefix="/discount-rules", tags=["Discount Rules"])


@router.get("", response_model=List[DiscountRuleResponse])
async def list_discount_rules(
    scope: Optional[DiscountScope] = None,
    is_active: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List discount rules configured for the organization.
    Supports filtering by scope (product vs subscription) and active status.
    Accessible to Staff and Admin.
    """
    return await DiscountService.list_discount_rules(
        session=db,
        organization_id=current_org.id,
        scope=scope,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=DiscountRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_discount_rule(
    data: DiscountRuleCreate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create a new discount rule: fixed amount or percentage, min purchase/qty,
    dates, max uses limit, and product or subscription scope.
    Restricted strictly to Admin role.
    """
    return await DiscountService.create_discount_rule(
        session=db,
        organization_id=current_org.id,
        data=data,
    )


@router.get("/{rule_id}", response_model=DiscountRuleResponse)
async def get_discount_rule(
    rule_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Retrieve discount rule details by ID.
    Accessible to Staff and Admin.
    """
    try:
        return await DiscountService.get_discount_rule(
            session=db,
            organization_id=current_org.id,
            rule_id=rule_id,
        )
    except DiscountRuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{rule_id}", response_model=DiscountRuleResponse)
async def update_discount_rule(
    rule_id: int,
    data: DiscountRuleUpdate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update discount parameters, thresholds, or usage limits.
    Restricted strictly to Admin role.
    """
    try:
        return await DiscountService.update_discount_rule(
            session=db,
            organization_id=current_org.id,
            rule_id=rule_id,
            data=data,
        )
    except DiscountRuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{rule_id}/archive", response_model=DiscountRuleResponse)
async def archive_discount_rule(
    rule_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Soft-archive a discount rule.
    Restricted strictly to Admin role.
    """
    try:
        return await DiscountService.archive_discount_rule(
            session=db,
            organization_id=current_org.id,
            rule_id=rule_id,
        )
    except DiscountRuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
