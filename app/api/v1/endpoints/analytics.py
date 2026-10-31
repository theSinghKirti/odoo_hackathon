"""
B9 Analytics API endpoints — Admin-only KPI aggregation routes.

All endpoints require Admin or Staff role (customers are denied).
Every query is automatically tenant-scoped via get_current_organization.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, get_current_user
from app.db.session import get_async_db
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.analytics import AnalyticsSummary, MRRBreakdown, OverdueInvoiceSummary
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _require_admin_or_staff(current_user: User) -> None:
    """Raise 403 if the caller is a customer-portal user."""
    if current_user.role == UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analytics are restricted to Admin and Staff users.",
        )


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    revenue_start: Optional[date] = Query(
        None,
        description="Inclusive start date for revenue-collected window (YYYY-MM-DD)",
    ),
    revenue_end: Optional[date] = Query(
        None,
        description="Inclusive end date for revenue-collected window (YYYY-MM-DD)",
    ),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> AnalyticsSummary:
    """
    Return the full KPI snapshot for the organization:

    - Active subscription count
    - MRR / ARR broken down by billing interval
    - Revenue collected (all time or within optional date window)
    - Overdue invoice count and total amount due
    """
    _require_admin_or_staff(current_user)
    return await AnalyticsService.get_summary(
        session=db,
        organization_id=current_org.id,
        revenue_start=revenue_start,
        revenue_end=revenue_end,
    )


@router.get("/subscriptions/active-count", response_model=dict)
async def get_active_subscription_count(
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """Return the count of active subscriptions for the organization."""
    _require_admin_or_staff(current_user)
    count = await AnalyticsService.get_active_subscriptions_count(
        session=db, organization_id=current_org.id
    )
    return {"active_subscriptions_count": count}


@router.get("/mrr-arr", response_model=MRRBreakdown)
async def get_mrr_arr(
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> MRRBreakdown:
    """
    Compute MRR and ARR from active subscription billing intervals.

    Formula (Business Rules §12):
      MRR = Σ(daily×30) + Σ(weekly×4.33) + Σ(monthly×1) + Σ(yearly÷12)
      ARR = MRR × 12
    """
    _require_admin_or_staff(current_user)
    return await AnalyticsService.get_mrr_arr(
        session=db, organization_id=current_org.id
    )


@router.get("/revenue", response_model=dict)
async def get_revenue_collected(
    start_date: Optional[date] = Query(
        None, description="Inclusive start date (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        None, description="Inclusive end date (YYYY-MM-DD)"
    ),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """Return total succeeded payment amounts within an optional date window."""
    _require_admin_or_staff(current_user)
    total = await AnalyticsService.get_revenue_collected(
        session=db,
        organization_id=current_org.id,
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "revenue_collected": total,
        "start_date": start_date,
        "end_date": end_date,
    }


@router.get("/invoices/overdue", response_model=OverdueInvoiceSummary)
async def get_overdue_invoices(
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> OverdueInvoiceSummary:
    """
    Return the count and total amount_due of confirmed invoices
    whose due_date is in the past.
    """
    _require_admin_or_staff(current_user)
    return await AnalyticsService.get_overdue_invoices(
        session=db, organization_id=current_org.id
    )

