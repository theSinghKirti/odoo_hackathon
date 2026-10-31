from datetime import date, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.invoice import Invoice, InvoiceLine, InvoiceStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.plan import BillingInterval, SubscriptionPlan
from app.models.product import Product, ProductType
from app.models.subscription import Subscription, SubscriptionLine, SubscriptionStatus
from app.models.user import UserRole
from app.schemas.payment import PaymentCreate, RazorpayVerifyRequest
from app.services.payment_service import (
    InvalidPaymentError,
    PaymentService,
    PaymentServiceError,
    PaymentVerificationError,
)
from tests.conftest import auth_header


@pytest.fixture
async def payment_setup(db_session: AsyncSession, seed_data: dict):
    org = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    customer_user = seed_data["customer_a"]

    cust.user_id = customer_user.id
    await db_session.commit()

    # Create active confirmed invoice with amount_due = 1500.00
    today = date.today()
    invoice = Invoice(
        organization_id=org.id,
        invoice_number=f"INV-{today.year}-9001",
        customer_id=cust.id,
        invoice_date=today,
        due_date=today + timedelta(days=15),
        status=InvoiceStatus.CONFIRMED,
        subtotal=Decimal("1500.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("1500.00"),
        amount_paid=Decimal("0.00"),
        amount_due=Decimal("1500.00"),
        notes="Setup test invoice",
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)

    return {
        "org": org,
        "customer": cust,
        "customer_user": customer_user,
        "invoice": invoice,
    }


# ==========================================
# 1. Offline Payment Service Tests
# ==========================================


async def test_record_offline_payment_full_amount(db_session: AsyncSession, payment_setup: dict, seed_data: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]
    staff = seed_data["staff_a"]

    data = PaymentCreate(
        payment_method=PaymentMethod.BANK_TRANSFER,
        amount=Decimal("1500.00"),
        payment_date=date.today(),
        note="NEFT ref UTR9988112233",
    )

    payment = await PaymentService.record_offline_payment(
        session=db_session,
        organization_id=org.id,
        invoice_id=inv.id,
        data=data,
        user=staff,
    )

    assert payment.id is not None
    assert payment.amount == Decimal("1500.00")
    assert payment.payment_method == PaymentMethod.BANK_TRANSFER
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.customer_id == inv.customer_id

    # Invoice fully settled
    await db_session.refresh(inv)
    assert inv.amount_paid == Decimal("1500.00")
    assert inv.amount_due == Decimal("0.00")
    assert inv.status == InvoiceStatus.PAID


async def test_record_offline_partial_payments(db_session: AsyncSession, payment_setup: dict, seed_data: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]
    staff = seed_data["staff_a"]

    # 1. First partial payment: 500
    p1 = await PaymentService.record_offline_payment(
        session=db_session,
        organization_id=org.id,
        invoice_id=inv.id,
        data=PaymentCreate(payment_method=PaymentMethod.CHEQUE, amount=Decimal("500.00"), note="Cheque 00123"),
        user=staff,
    )
    assert p1.amount == Decimal("500.00")
    await db_session.refresh(inv)
    assert inv.amount_paid == Decimal("500.00")
    assert inv.amount_due == Decimal("1000.00")
    assert inv.status == InvoiceStatus.CONFIRMED

    # 2. Second partial payment: 1000
    p2 = await PaymentService.record_offline_payment(
        session=db_session,
        organization_id=org.id,
        invoice_id=inv.id,
        data=PaymentCreate(payment_method=PaymentMethod.CASH, amount=Decimal("1000.00"), note="Cash payment"),
        user=staff,
    )
    assert p2.amount == Decimal("1000.00")
    await db_session.refresh(inv)
    assert inv.amount_paid == Decimal("1500.00")
    assert inv.amount_due == Decimal("0.00")
    assert inv.status == InvoiceStatus.PAID


async def test_record_payment_excess_amount_fails(db_session: AsyncSession, payment_setup: dict, seed_data: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]
    staff = seed_data["staff_a"]

    with pytest.raises(InvalidPaymentError, match="cannot exceed remaining amount due"):
        await PaymentService.record_offline_payment(
            session=db_session,
            organization_id=org.id,
            invoice_id=inv.id,
            data=PaymentCreate(payment_method=PaymentMethod.BANK_TRANSFER, amount=Decimal("1500.01")),
            user=staff,
        )


async def test_record_payment_already_paid_fails(db_session: AsyncSession, payment_setup: dict, seed_data: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]
    staff = seed_data["staff_a"]

    inv.status = InvoiceStatus.PAID
    inv.amount_paid = Decimal("1500.00")
    inv.amount_due = Decimal("0.00")
    await db_session.commit()

    with pytest.raises(InvalidPaymentError, match="already fully paid"):
        await PaymentService.record_offline_payment(
            session=db_session,
            organization_id=org.id,
            invoice_id=inv.id,
            data=PaymentCreate(payment_method=PaymentMethod.CASH, amount=Decimal("100.00")),
            user=staff,
        )


async def test_customer_cannot_record_offline_payment(db_session: AsyncSession, payment_setup: dict, seed_data: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]
    cust_user = seed_data["customer_a"]

    with pytest.raises(PaymentServiceError, match="not authorized"):
        await PaymentService.record_offline_payment(
            session=db_session,
            organization_id=org.id,
            invoice_id=inv.id,
            data=PaymentCreate(payment_method=PaymentMethod.CASH, amount=Decimal("100.00")),
            user=cust_user,
        )


# ==========================================
# 2. Online Razorpay Integration Tests
# ==========================================


async def test_create_razorpay_order(db_session: AsyncSession, payment_setup: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]

    order = await PaymentService.create_razorpay_order(
        session=db_session,
        organization_id=org.id,
        invoice_id=inv.id,
    )

    assert order.order_id.startswith("order_")
    # 1500.00 INR = 150000 paise
    assert order.amount == 150000
    assert order.currency == "INR"
    assert order.invoice_id == inv.id
    assert order.invoice_number == inv.invoice_number


async def test_verify_razorpay_payment_valid_signature(db_session: AsyncSession, payment_setup: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]

    order_id = "order_mock1234567"
    payment_id = "pay_mock9876543"

    # Compute valid HMAC-SHA256 signature
    msg = f"{order_id}|{payment_id}"
    valid_sig = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    payment = await PaymentService.verify_razorpay_payment(
        session=db_session,
        organization_id=org.id,
        invoice_id=inv.id,
        razorpay_order_id=order_id,
        razorpay_payment_id=payment_id,
        razorpay_signature=valid_sig,
    )

    assert payment.id is not None
    assert payment.payment_method == PaymentMethod.RAZORPAY
    assert payment.razorpay_payment_id == payment_id
    assert payment.status == PaymentStatus.SUCCEEDED

    await db_session.refresh(inv)
    assert inv.status == InvoiceStatus.PAID
    assert inv.amount_paid == Decimal("1500.00")
    assert inv.amount_due == Decimal("0.00")


async def test_verify_razorpay_payment_invalid_signature_fails(db_session: AsyncSession, payment_setup: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]

    with pytest.raises(PaymentVerificationError, match="Invalid Razorpay HMAC-SHA256 signature"):
        await PaymentService.verify_razorpay_payment(
            session=db_session,
            organization_id=org.id,
            invoice_id=inv.id,
            razorpay_order_id="order_123",
            razorpay_payment_id="pay_456",
            razorpay_signature="invalid_tampered_signature_hex",
        )

    await db_session.refresh(inv)
    assert inv.status == InvoiceStatus.CONFIRMED
    assert inv.amount_paid == Decimal("0.00")


async def test_verify_razorpay_payment_idempotency(db_session: AsyncSession, payment_setup: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]

    order_id = "order_idem123"
    payment_id = "pay_idem999"
    msg = f"{order_id}|{payment_id}"
    valid_sig = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # First verification
    p1 = await PaymentService.verify_razorpay_payment(
        session=db_session,
        organization_id=org.id,
        invoice_id=inv.id,
        razorpay_order_id=order_id,
        razorpay_payment_id=payment_id,
        razorpay_signature=valid_sig,
    )

    # Second verification with identical payment_id (idempotent replay)
    p2 = await PaymentService.verify_razorpay_payment(
        session=db_session,
        organization_id=org.id,
        invoice_id=inv.id,
        razorpay_order_id=order_id,
        razorpay_payment_id=payment_id,
        razorpay_signature=valid_sig,
    )

    assert p1.id == p2.id
    await db_session.refresh(inv)
    # Amount paid should still be 1500, not double-credited 3000!
    assert inv.amount_paid == Decimal("1500.00")


# ==========================================
# 3. Webhook Tests
# ==========================================


async def test_razorpay_webhook_processing(db_session: AsyncSession, payment_setup: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]

    payload = {
        "event": "payment.captured",
        "id": "evt_test123456",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_wh778899",
                    "order_id": "order_wh778899",
                    "amount": 150000,
                    "currency": "INR",
                    "status": "captured",
                    "notes": {
                        "organization_id": str(org.id),
                        "invoice_id": str(inv.id),
                    },
                }
            }
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    valid_sig = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    # Process webhook
    res = await PaymentService.handle_razorpay_webhook(
        session=db_session,
        payload_bytes=payload_bytes,
        signature=valid_sig,
    )
    assert res["status"] == "processed"

    await db_session.refresh(inv)
    assert inv.status == InvoiceStatus.PAID
    assert inv.amount_paid == Decimal("1500.00")

    # Second processing of same webhook -> idempotent ignore
    res_dup = await PaymentService.handle_razorpay_webhook(
        session=db_session,
        payload_bytes=payload_bytes,
        signature=valid_sig,
    )
    assert res_dup["status"] == "ignored"


# ==========================================
# 4. REST API Endpoint Tests
# ==========================================


async def test_api_record_offline_payment_staff(client: AsyncClient, payment_setup: dict, seed_data: dict):
    staff_headers = auth_header(seed_data["staff_a"])
    inv = payment_setup["invoice"]

    res = await client.post(
        f"/api/v1/invoices/{inv.id}/payments",
        json={
            "payment_method": "bank_transfer",
            "amount": "1500.00",
            "note": "API recorded NEFT",
        },
        headers=staff_headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["amount"] == "1500.00"
    assert data["payment_method"] == "bank_transfer"
    assert data["status"] == "succeeded"


async def test_api_record_offline_payment_customer_forbidden(client: AsyncClient, payment_setup: dict, seed_data: dict):
    cust_headers = auth_header(seed_data["customer_a"])
    inv = payment_setup["invoice"]

    res = await client.post(
        f"/api/v1/invoices/{inv.id}/payments",
        json={
            "payment_method": "cash",
            "amount": "100.00",
        },
        headers=cust_headers,
    )
    assert res.status_code == 403


async def test_api_portal_order_and_verify(client: AsyncClient, payment_setup: dict, seed_data: dict):
    cust_headers = auth_header(seed_data["customer_a"])
    inv = payment_setup["invoice"]

    # 1. Initiate order
    order_res = await client.post(
        f"/api/v1/portal/invoices/{inv.id}/razorpay/order",
        headers=cust_headers,
    )
    assert order_res.status_code == 200
    order_data = order_res.json()
    order_id = order_data["order_id"]
    assert order_data["amount"] == 150000

    # 2. Verify signature
    payment_id = "pay_api_test_001"
    msg = f"{order_id}|{payment_id}"
    sig = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    verify_res = await client.post(
        f"/api/v1/portal/invoices/{inv.id}/razorpay/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": sig,
        },
        headers=cust_headers,
    )
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["status"] == "success"
    assert verify_data["invoice_status"] == "paid"
    assert Decimal(str(verify_data["amount_due"])) == Decimal("0.00")


async def test_api_webhook_endpoint(client: AsyncClient, payment_setup: dict):
    setup = payment_setup
    org = setup["org"]
    inv = setup["invoice"]

    payload = {
        "event": "payment.captured",
        "id": "evt_api_hook_99",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_hook_99",
                    "order_id": "order_hook_99",
                    "amount": 150000,
                    "currency": "INR",
                    "notes": {
                        "organization_id": str(org.id),
                        "invoice_id": str(inv.id),
                    },
                }
            }
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    res = await client.post(
        "/api/v1/webhooks/razorpay",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "processed"
