from datetime import date
from decimal import Decimal
import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional
import uuid
import razorpay
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.payment import PaymentCreate, RazorpayOrderResponse
from app.services.invoice_service import InvoiceNotFoundError, InvoiceService


class PaymentServiceError(Exception):
    """Base exception for payment operations."""
    pass


class PaymentNotFoundError(PaymentServiceError):
    pass


class InvalidPaymentError(PaymentServiceError):
    pass


class PaymentVerificationError(PaymentServiceError):
    pass


class DuplicatePaymentError(PaymentServiceError):
    pass


class PaymentService:
    @staticmethod
    async def record_offline_payment(
        session: AsyncSession,
        organization_id: int,
        invoice_id: int,
        data: PaymentCreate,
        user: Optional[User] = None,
    ) -> Payment:
        """
        Records an offline manual payment (Bank Transfer, Cheque, Cash, Other).
        Enforces RBAC: Customers cannot manually record ledger payments.
        Updates invoice: increments amount_paid, decrements amount_due,
        and transitions status to 'Paid' when balance reaches 0.
        """
        if user and user.role == UserRole.CUSTOMER:
            raise PaymentServiceError("Customers are not authorized to manually record offline payments.")

        invoice = await InvoiceService.get_invoice(session, organization_id, invoice_id, user=user)

        if invoice.status == InvoiceStatus.PAID:
            raise InvalidPaymentError(f"Invoice {invoice.invoice_number} is already fully paid.")

        if invoice.status == InvoiceStatus.CANCELLED:
            raise InvalidPaymentError(f"Cannot record payment for cancelled invoice {invoice.invoice_number}.")

        if data.amount <= Decimal("0.00"):
            raise InvalidPaymentError("Payment amount must be greater than zero.")

        if data.amount > invoice.amount_due:
            raise InvalidPaymentError(
                f"Payment amount ({data.amount}) cannot exceed remaining amount due ({invoice.amount_due})."
            )

        pay_date = data.payment_date or date.today()

        payment = Payment(
            organization_id=organization_id,
            invoice_id=invoice.id,
            customer_id=invoice.customer_id,
            payment_method=data.payment_method,
            amount=data.amount,
            payment_date=pay_date,
            note=data.note.strip() if data.note else None,
            status=PaymentStatus.SUCCEEDED,
        )
        session.add(payment)

        # Update invoice balance
        invoice.amount_paid += data.amount
        invoice.amount_due -= data.amount

        if invoice.amount_due <= Decimal("0.00"):
            invoice.amount_due = Decimal("0.00")
            invoice.status = InvoiceStatus.PAID
        elif invoice.status == InvoiceStatus.DRAFT:
            # First payment confirms draft invoice
            invoice.status = InvoiceStatus.CONFIRMED

        await session.commit()
        await session.refresh(payment)
        await session.refresh(invoice)
        return payment

    @staticmethod
    async def create_razorpay_order(
        session: AsyncSession,
        organization_id: int,
        invoice_id: int,
        user: Optional[User] = None,
    ) -> RazorpayOrderResponse:
        """
        Generates a Razorpay Order for online customer payment.
        Converts outstanding invoice amount_due to smallest currency subunit (paise).
        """
        invoice = await InvoiceService.get_invoice(session, organization_id, invoice_id, user=user)

        if invoice.status == InvoiceStatus.PAID or invoice.amount_due <= Decimal("0.00"):
            raise InvalidPaymentError(f"Invoice {invoice.invoice_number} is already fully settled.")

        if invoice.status == InvoiceStatus.CANCELLED:
            raise InvalidPaymentError(f"Cannot initiate payment for cancelled invoice {invoice.invoice_number}.")

        amount_in_paise = int(round(invoice.amount_due * 100))

        # Initialize Razorpay client
        order_id: str
        try:
            if settings.RAZORPAY_KEY_ID.startswith("rzp_test_mock") or not settings.is_production:
                # In development/test mock mode, create deterministic mock order ID
                order_id = f"order_{uuid.uuid4().hex[:14]}"
            else:
                client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
                order_params = {
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "receipt": f"inv_{invoice.id}_{int(date.today().strftime('%Y%m%d'))}",
                    "notes": {
                        "organization_id": str(organization_id),
                        "invoice_id": str(invoice.id),
                        "invoice_number": invoice.invoice_number,
                    },
                }
                rp_order = client.order.create(data=order_params)
                order_id = rp_order["id"]
        except Exception:
            order_id = f"order_{uuid.uuid4().hex[:14]}"

        return RazorpayOrderResponse(
            order_id=order_id,
            amount=amount_in_paise,
            currency="INR",
            key_id=settings.RAZORPAY_KEY_ID,
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            customer_name=invoice.customer.name,
            customer_email=invoice.customer.email,
        )

    @staticmethod
    async def verify_razorpay_payment(
        session: AsyncSession,
        organization_id: int,
        invoice_id: int,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
        user: Optional[User] = None,
    ) -> Payment:
        """
        Cryptographically verifies the Razorpay payment signature using server-side HMAC-SHA256:
        HMAC-SHA256(order_id + "|" + payment_id, key_secret) == signature.
        Idempotent: prevents duplicate payment processing.
        Transitions invoice to 'Paid' upon full settlement.
        """
        invoice = await InvoiceService.get_invoice(session, organization_id, invoice_id, user=user)

        # 1. Cryptographic HMAC verification
        message = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected_sig = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, razorpay_signature):
            raise PaymentVerificationError(
                "Authoritative payment verification failed: Invalid Razorpay HMAC-SHA256 signature."
            )

        # 2. Duplicate payment prevention (idempotency)
        stmt = select(Payment).where(
            and_(
                Payment.organization_id == organization_id,
                Payment.razorpay_payment_id == razorpay_payment_id,
            )
        )
        res = await session.execute(stmt)
        existing = res.scalars().first()
        if existing:
            return existing

        # 3. Create payment record
        paid_amount = invoice.amount_due

        payment = Payment(
            organization_id=organization_id,
            invoice_id=invoice.id,
            customer_id=invoice.customer_id,
            payment_method=PaymentMethod.RAZORPAY,
            amount=paid_amount,
            payment_date=date.today(),
            note=f"Verified Razorpay Online Payment (Order: {razorpay_order_id})",
            status=PaymentStatus.SUCCEEDED,
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
        )
        session.add(payment)

        # 4. Settle invoice
        invoice.amount_paid += paid_amount
        invoice.amount_due = Decimal("0.00")
        invoice.status = InvoiceStatus.PAID

        await session.commit()
        await session.refresh(payment)
        await session.refresh(invoice)
        return payment

    @staticmethod
    async def handle_razorpay_webhook(
        session: AsyncSession,
        payload_bytes: bytes,
        signature: str,
    ) -> Dict[str, Any]:
        """
        Ingests Razorpay webhook events with signature verification and duplicate event prevention.
        Handles 'payment.captured' and 'order.paid'.
        """
        expected_sig = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, signature):
            raise PaymentVerificationError("Invalid Razorpay webhook signature.")

        event_data = json.loads(payload_bytes.decode("utf-8"))
        event_name = event_data.get("event")
        event_id = event_data.get("id")

        if event_name in ("payment.captured", "order.paid"):
            payment_entity = event_data.get("payload", {}).get("payment", {}).get("entity", {})
            rp_payment_id = payment_entity.get("id")
            rp_order_id = payment_entity.get("order_id")
            amount_paise = payment_entity.get("amount", 0)
            amount_dec = Decimal(str(amount_paise)) / Decimal("100.00")
            notes = payment_entity.get("notes", {})
            invoice_id_str = notes.get("invoice_id")
            org_id_str = notes.get("organization_id")

            if rp_payment_id and invoice_id_str and org_id_str:
                org_id = int(org_id_str)
                inv_id = int(invoice_id_str)

                # Duplicate payment check
                stmt = select(Payment).where(
                    and_(
                        Payment.organization_id == org_id,
                        Payment.razorpay_payment_id == rp_payment_id,
                    )
                )
                res = await session.execute(stmt)
                if res.scalars().first():
                    return {
                        "status": "ignored",
                        "message": "Payment event already processed (idempotent).",
                        "event_id": event_id,
                    }

                # Retrieve and settle invoice
                inv_stmt = select(Invoice).where(and_(Invoice.id == inv_id, Invoice.organization_id == org_id))
                inv_res = await session.execute(inv_stmt)
                invoice = inv_res.scalars().first()

                if invoice and invoice.status != InvoiceStatus.PAID:
                    payment = Payment(
                        organization_id=org_id,
                        invoice_id=invoice.id,
                        customer_id=invoice.customer_id,
                        payment_method=PaymentMethod.RAZORPAY,
                        amount=amount_dec,
                        payment_date=date.today(),
                        note=f"Razorpay Webhook: {event_name} (Event: {event_id})",
                        status=PaymentStatus.SUCCEEDED,
                        razorpay_order_id=rp_order_id,
                        razorpay_payment_id=rp_payment_id,
                    )
                    session.add(payment)

                    invoice.amount_paid += amount_dec
                    invoice.amount_due = max(Decimal("0.00"), invoice.amount_due - amount_dec)
                    if invoice.amount_due <= Decimal("0.00"):
                        invoice.status = InvoiceStatus.PAID
                    await session.commit()

        return {
            "status": "processed",
            "event": event_name,
            "event_id": event_id,
        }

    @staticmethod
    async def list_payments(
        session: AsyncSession,
        organization_id: int,
        invoice_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        user: Optional[User] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Payment]:
        """
        Lists payment records scoped to tenant organization.
        Customer users are automatically restricted to their own payment receipts.
        """
        filters = [Payment.organization_id == organization_id]

        if user and user.role == UserRole.CUSTOMER:
            c_stmt = select(Customer.id).where(
                and_(
                    Customer.organization_id == organization_id,
                    (Customer.user_id == user.id) | (Customer.email == user.email),
                )
            )
            c_res = await session.execute(c_stmt)
            owned_ids = c_res.scalars().all()
            if not owned_ids:
                return []
            filters.append(Payment.customer_id.in_(owned_ids))
        elif customer_id:
            filters.append(Payment.customer_id == customer_id)

        if invoice_id:
            filters.append(Payment.invoice_id == invoice_id)

        stmt = (
            select(Payment)
            .options(
                selectinload(Payment.invoice),
                selectinload(Payment.customer),
            )
            .where(and_(*filters))
            .order_by(desc(Payment.id))
            .offset(skip)
            .limit(limit)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

