from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, get_current_user
from app.db.session import get_async_db
from app.models.invoice import InvoiceStatus
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.invoice import (
    BillingSweepRequest,
    BillingSweepResponse,
    InvoiceCancelRequest,
    InvoiceResponse,
)
from app.services.invoice_service import (
    InvalidInvoiceStateError,
    InvoiceAccessDeniedError,
    InvoiceNotFoundError,
    InvoiceService,
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.get("", response_model=List[InvoiceResponse])
async def list_invoices(
    status_filter: Optional[InvoiceStatus] = Query(None, alias="status"),
    customer_id: Optional[int] = None,
    subscription_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List invoices for the organization.
    Customer portal users are automatically restricted to their own invoices.
    """
    return await InvoiceService.list_invoices(
        session=db,
        organization_id=current_org.id,
        status=status_filter,
        customer_id=customer_id,
        subscription_id=subscription_id,
        user=current_user,
        skip=skip,
        limit=limit,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Retrieve invoice details, line items, customer, and subscription context.
    """
    try:
        return await InvoiceService.get_invoice(
            session=db,
            organization_id=current_org.id,
            invoice_id=invoice_id,
            user=current_user,
        )
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvoiceAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/{invoice_id}/confirm", response_model=InvoiceResponse)
async def confirm_invoice(
    invoice_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Confirm a Draft invoice, locking its line items (Staff/Admin only).
    """
    if current_user.role == UserRole.CUSTOMER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customers cannot confirm invoices.")
    try:
        return await InvoiceService.confirm_invoice(
            session=db,
            organization_id=current_org.id,
            invoice_id=invoice_id,
            user=current_user,
        )
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidInvoiceStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: int,
    data: Optional[InvoiceCancelRequest] = None,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Cancel an unpaid Draft or Confirmed invoice (Staff/Admin only).
    """
    if current_user.role == UserRole.CUSTOMER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customers cannot cancel invoices.")
    try:
        reason = data.reason if data else None
        return await InvoiceService.cancel_invoice(
            session=db,
            organization_id=current_org.id,
            invoice_id=invoice_id,
            reason=reason,
            user=current_user,
        )
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidInvoiceStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/from-subscription/{subscription_id}", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def generate_invoice_for_subscription(
    subscription_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Manually generate an invoice from an active subscription (Staff/Admin only).
    """
    if current_user.role == UserRole.CUSTOMER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customers cannot generate invoices.")
    try:
        return await InvoiceService.create_invoice_for_subscription(
            session=db,
            organization_id=current_org.id,
            subscription_id=subscription_id,
        )
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidInvoiceStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/sweep", response_model=BillingSweepResponse)
async def trigger_billing_sweep(
    data: Optional[BillingSweepRequest] = None,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Trigger an automated billing sweep across subscriptions due as of the target date (Staff/Admin only).
    """
    if current_user.role == UserRole.CUSTOMER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customers cannot trigger billing sweeps.")

    as_of = data.as_of_date if data and data.as_of_date else None
    invoices = await InvoiceService.run_billing_sweep(
        session=db,
        as_of_date=as_of,
        organization_id=current_org.id,
    )

    total_amount = sum(inv.total_amount for inv in invoices)
    return BillingSweepResponse(
        as_of_date=as_of or invoices[0].invoice_date if invoices else (as_of or current_org.created_at.date()),
        subscriptions_evaluated=len(invoices),
        invoices_generated=len(invoices),
        total_billed_amount=total_amount,
        invoice_ids=[inv.id for inv in invoices],
    )

