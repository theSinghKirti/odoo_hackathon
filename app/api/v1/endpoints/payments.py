from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, get_current_user
from app.db.session import get_async_db
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.payment import (
    PaymentCreate,
    PaymentResponse,
    RazorpayOrderResponse,
    RazorpayVerifyRequest,
    RazorpayVerifyResponse,
)
from app.services.invoice_service import InvoiceNotFoundError
from app.services.payment_service import (
    InvalidPaymentError,
    PaymentService,
    PaymentServiceError,
    PaymentVerificationError,
)

router = APIRouter(tags=["Payments"])


@router.post("/invoices/{invoice_id}/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def record_offline_payment(
    invoice_id: int,
    data: PaymentCreate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Record an offline payment (Bank Transfer, Cheque, Cash) against an invoice.
    Restricted to Admin and Staff roles.
    """
    if current_user.role == UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customers are not authorized to manually record offline payments.",
        )
    try:
        return await PaymentService.record_offline_payment(
            session=db,
            organization_id=current_org.id,
            invoice_id=invoice_id,
            data=data,
            user=current_user,
        )
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidPaymentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PaymentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/invoices/{invoice_id}/payments", response_model=List[PaymentResponse])
async def list_invoice_payments(
    invoice_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List all payment ledger records for a specific invoice.
    """
    return await PaymentService.list_payments(
        session=db,
        organization_id=current_org.id,
        invoice_id=invoice_id,
        user=current_user,
    )


@router.get("/payments", response_model=List[PaymentResponse])
async def list_payments(
    customer_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List payment records for the organization.
    Customer portal users are automatically restricted to their own payment receipts.
    """
    return await PaymentService.list_payments(
        session=db,
        organization_id=current_org.id,
        customer_id=customer_id,
        user=current_user,
        skip=skip,
        limit=limit,
    )


@router.post("/portal/invoices/{invoice_id}/razorpay/order", response_model=RazorpayOrderResponse)
async def create_razorpay_order(
    invoice_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Initiates an online payment order with Razorpay for an outstanding invoice.
    """
    try:
        return await PaymentService.create_razorpay_order(
            session=db,
            organization_id=current_org.id,
            invoice_id=invoice_id,
            user=current_user,
        )
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidPaymentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/portal/invoices/{invoice_id}/razorpay/verify", response_model=RazorpayVerifyResponse)
async def verify_razorpay_payment(
    invoice_id: int,
    data: RazorpayVerifyRequest,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Authoritatively verifies server-side HMAC-SHA256 signature for completed Razorpay checkout.
    Settles invoice balance and returns confirmation.
    """
    try:
        payment = await PaymentService.verify_razorpay_payment(
            session=db,
            organization_id=current_org.id,
            invoice_id=invoice_id,
            razorpay_order_id=data.razorpay_order_id,
            razorpay_payment_id=data.razorpay_payment_id,
            razorpay_signature=data.razorpay_signature,
            user=current_user,
        )
        return RazorpayVerifyResponse(
            status="success",
            message="Payment successfully verified and settled.",
            payment_id=payment.id,
            invoice_id=payment.invoice_id,
            amount_paid=payment.invoice.amount_paid,
            amount_due=payment.invoice.amount_due,
            invoice_status=payment.invoice.status.value,
        )
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PaymentVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """
    Razorpay Webhook receiver for payment events with duplicate event prevention.
    """
    if not x_razorpay_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Razorpay-Signature header.")

    payload_bytes = await request.body()
    try:
        return await PaymentService.handle_razorpay_webhook(
            session=db,
            payload_bytes=payload_bytes,
            signature=x_razorpay_signature,
        )
    except PaymentVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

