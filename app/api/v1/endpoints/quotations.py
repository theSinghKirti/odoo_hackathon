from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, require_staff_or_admin
from app.db.session import get_async_db
from app.models.organization import Organization
from app.models.quotation import QuotationStatus
from app.models.user import User
from app.schemas.quotation import (
    QuotationCreate,
    QuotationResponse,
    QuotationStatusUpdate,
)
from app.schemas.subscription import SubscriptionResponse
from app.services.plan_service import PlanNotAvailableError, QuantityBelowMinimumError
from app.services.quotation_service import (
    CustomerNotFoundError,
    InvalidQuotationStateError,
    ProductOrVariantNotFoundError,
    QuotationNotFoundError,
    QuotationService,
    QuotationServiceError,
)

router = APIRouter(prefix="/quotations", tags=["Quotations"])


@router.get("", response_model=List[QuotationResponse])
async def list_quotations(
    customer_id: Optional[int] = None,
    status_filter: Optional[QuotationStatus] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List quotations with optional customer and status filters.
    Accessible to Staff and Admin.
    """
    return await QuotationService.list_quotations(
        session=db,
        organization_id=current_org.id,
        customer_id=customer_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=QuotationResponse, status_code=status.HTTP_201_CREATED)
async def create_quotation(
    data: QuotationCreate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create a new quotation. Supports copying from template or building custom lines.
    Calculates line-level surcharge math, taxes, discounts, and expiry date.
    Accessible to Staff and Admin.
    """
    try:
        return await QuotationService.create_quotation(
            session=db,
            organization_id=current_org.id,
            data=data,
        )
    except (CustomerNotFoundError, ProductOrVariantNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except QuotationServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{quotation_id}", response_model=QuotationResponse)
async def get_quotation(
    quotation_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Retrieve full quotation details including lines, customer, and plan."""
    try:
        return await QuotationService.get_quotation(
            session=db,
            organization_id=current_org.id,
            quotation_id=quotation_id,
        )
    except QuotationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{quotation_id}/status", response_model=QuotationResponse)
async def update_quotation_status(
    quotation_id: int,
    data: QuotationStatusUpdate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update quotation status (e.g. from Draft -> Quotation -> Confirmed).
    """
    try:
        return await QuotationService.update_quotation_status(
            session=db,
            organization_id=current_org.id,
            quotation_id=quotation_id,
            new_status=data.status,
        )
    except QuotationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidQuotationStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{quotation_id}/convert", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def convert_to_subscription(
    quotation_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    ATOMIC CONVERSION ENDPOINT:
    Converts a confirmed/delivered quotation into an Active recurring Subscription.
    Copies lines, plan policies, computes initial next_billing_date, and flags quotation CONVERTED.
    """
    try:
        return await QuotationService.convert_quotation_to_subscription(
            session=db,
            organization_id=current_org.id,
            quotation_id=quotation_id,
        )
    except QuotationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidQuotationStateError, QuantityBelowMinimumError, PlanNotAvailableError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
