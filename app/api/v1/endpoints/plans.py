from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, require_admin, require_staff_or_admin
from app.db.session import get_async_db
from app.models.organization import Organization
from app.models.plan import BillingInterval
from app.models.user import User
from app.schemas.plan import PlanCreate, PlanResponse, PlanUpdate
from app.services.plan_service import PlanNotFoundError, PlanService

router = APIRouter(prefix="/plans", tags=["Subscription Plans"])


@router.get("", response_model=List[PlanResponse])
async def list_plans(
    billing_interval: Optional[BillingInterval] = None,
    is_active: Optional[bool] = None,
    available_only: bool = Query(False, description="Filter only plans available today"),
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List subscription plans for the organization.
    Supports filtering by billing_interval (daily, weekly, monthly, yearly), active status, search, and availability.
    Accessible to Staff and Admin.
    """
    plans = await PlanService.list_plans(
        session=db,
        organization_id=current_org.id,
        billing_interval=billing_interval,
        is_active=is_active,
        available_only=available_only,
        search=search,
        skip=skip,
        limit=limit,
    )
    return [PlanResponse.from_orm_with_availability(p) for p in plans]


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    data: PlanCreate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create a new subscription plan with billing frequency and lifecycle policies.
    Restricted strictly to Admin role.
    """
    plan = await PlanService.create_plan(
        session=db,
        organization_id=current_org.id,
        data=data,
    )
    return PlanResponse.from_orm_with_availability(plan)


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Retrieve plan details and lifecycle rules by ID.
    Accessible to Staff and Admin.
    """
    try:
        plan = await PlanService.get_plan(
            session=db,
            organization_id=current_org.id,
            plan_id=plan_id,
        )
        return PlanResponse.from_orm_with_availability(plan)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: int,
    data: PlanUpdate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update subscription plan parameters or lifecycle rules.
    Restricted strictly to Admin role.
    """
    try:
        plan = await PlanService.update_plan(
            session=db,
            organization_id=current_org.id,
            plan_id=plan_id,
            data=data,
        )
        return PlanResponse.from_orm_with_availability(plan)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{plan_id}/archive", response_model=PlanResponse)
async def archive_plan(
    plan_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Soft-archive a plan (sets is_active=False).
    Prevents new subscriptions while preserving existing historical subscriptions.
    Restricted strictly to Admin role.
    """
    try:
        plan = await PlanService.archive_plan(
            session=db,
            organization_id=current_org.id,
            plan_id=plan_id,
        )
        return PlanResponse.from_orm_with_availability(plan)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
