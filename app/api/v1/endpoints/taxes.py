from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, require_admin, require_staff_or_admin
from app.db.session import get_async_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.tax import TaxRuleCreate, TaxRuleResponse, TaxRuleUpdate
from app.services.tax_service import TaxRuleNotFoundError, TaxService

router = APIRouter(prefix="/tax-rules", tags=["Tax Rules"])


@router.get("", response_model=List[TaxRuleResponse])
async def list_tax_rules(
    is_active: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List configured tax rules for the organization.
    Accessible to Staff and Admin.
    """
    return await TaxService.list_tax_rules(
        session=db,
        organization_id=current_org.id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=TaxRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_tax_rule(
    data: TaxRuleCreate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create a new tax rule with percentage rate.
    Restricted strictly to Admin role.
    """
    return await TaxService.create_tax_rule(
        session=db,
        organization_id=current_org.id,
        data=data,
    )


@router.get("/{rule_id}", response_model=TaxRuleResponse)
async def get_tax_rule(
    rule_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Retrieve tax rule details by ID.
    Accessible to Staff and Admin.
    """
    try:
        return await TaxService.get_tax_rule(
            session=db,
            organization_id=current_org.id,
            tax_rule_id=rule_id,
        )
    except TaxRuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{rule_id}", response_model=TaxRuleResponse)
async def update_tax_rule(
    rule_id: int,
    data: TaxRuleUpdate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update tax rule rate, name, or active status.
    Restricted strictly to Admin role.
    """
    try:
        return await TaxService.update_tax_rule(
            session=db,
            organization_id=current_org.id,
            tax_rule_id=rule_id,
            data=data,
        )
    except TaxRuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{rule_id}/archive", response_model=TaxRuleResponse)
async def archive_tax_rule(
    rule_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Soft-archive a tax rule.
    Restricted strictly to Admin role.
    """
    try:
        return await TaxService.archive_tax_rule(
            session=db,
            organization_id=current_org.id,
            tax_rule_id=rule_id,
        )
    except TaxRuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
