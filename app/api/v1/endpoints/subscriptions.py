from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, get_current_user
from app.db.session import get_async_db
from app.models.organization import Organization
from app.models.subscription import SubscriptionStatus
from app.models.user import User
from app.schemas.subscription import SubscriptionCloseRequest, SubscriptionResponse
from app.services.subscription_service import (
    InvalidSubscriptionStateError,
    SubscriptionAccessDeniedError,
    SubscriptionNotFoundError,
    SubscriptionPolicyViolationError,
    SubscriptionService,
)

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("", response_model=List[SubscriptionResponse])
async def list_subscriptions(
    status_filter: Optional[SubscriptionStatus] = Query(None, alias="status"),
    customer_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List subscriptions with optional status and customer filters.
    Staff/Admin can view all organization subscriptions.
    Customer users are automatically restricted to their own subscriptions.
    """
    return await SubscriptionService.list_subscriptions(
        session=db,
        organization_id=current_org.id,
        status=status_filter,
        customer_id=customer_id,
        user=current_user,
        skip=skip,
        limit=limit,
    )


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Retrieve subscription details and line items.
    Enforces customer ownership check.
    """
    try:
        return await SubscriptionService.get_subscription(
            session=db,
            organization_id=current_org.id,
            subscription_id=subscription_id,
            user=current_user,
        )
    except SubscriptionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SubscriptionAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/{subscription_id}/pause", response_model=SubscriptionResponse)
async def pause_subscription(
    subscription_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Pauses an Active subscription.
    Enforces allow_pause policy toggle. Suspends automated billing.
    """
    try:
        return await SubscriptionService.pause_subscription(
            session=db,
            organization_id=current_org.id,
            subscription_id=subscription_id,
            user=current_user,
        )
    except SubscriptionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SubscriptionAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (InvalidSubscriptionStateError, SubscriptionPolicyViolationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{subscription_id}/resume", response_model=SubscriptionResponse)
async def resume_subscription(
    subscription_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Resumes a Paused subscription back to Active.
    Recalculates next_billing_date if due date passed while paused.
    """
    try:
        return await SubscriptionService.resume_subscription(
            session=db,
            organization_id=current_org.id,
            subscription_id=subscription_id,
            user=current_user,
        )
    except SubscriptionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SubscriptionAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidSubscriptionStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{subscription_id}/close", response_model=SubscriptionResponse)
async def close_subscription(
    subscription_id: int,
    body: Optional[SubscriptionCloseRequest] = None,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Closes a subscription. Terminal state.
    Enforces allow_early_close policy toggle if closed before expiry.
    """
    reason = body.reason if body else None
    try:
        return await SubscriptionService.close_subscription(
            session=db,
            organization_id=current_org.id,
            subscription_id=subscription_id,
            user=current_user,
            reason=reason,
        )
    except SubscriptionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SubscriptionAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (InvalidSubscriptionStateError, SubscriptionPolicyViolationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{subscription_id}/renew", response_model=SubscriptionResponse)
async def renew_subscription(
    subscription_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Renews an active or closed subscription for an additional billing cycle.
    Enforces allow_renewal policy toggle.
    """
    try:
        return await SubscriptionService.renew_subscription(
            session=db,
            organization_id=current_org.id,
            subscription_id=subscription_id,
            user=current_user,
        )
    except SubscriptionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SubscriptionAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except SubscriptionPolicyViolationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
