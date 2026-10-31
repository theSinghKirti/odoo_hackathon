from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.discount import DiscountRule, DiscountScope, DiscountType
from app.models.invoice import Invoice, InvoiceLine, InvoiceStatus
from app.models.plan import BillingInterval, SubscriptionPlan
from app.models.product import Product, ProductType
from app.models.subscription import Subscription, SubscriptionLine, SubscriptionStatus
from app.models.tax import TaxRule
from app.services.invoice_service import (
    InvalidInvoiceStateError,
    InvoiceAccessDeniedError,
    InvoiceNotFoundError,
    InvoiceService,
)
from app.workers.billing_tasks import run_daily_billing_sweep
from tests.conftest import auth_header


@pytest.fixture
async def sample_invoice_setup(db_session: AsyncSession, seed_data: dict):
    org = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    customer_user = seed_data["customer_a"]

    # Link customer_a user to cust_record_a
    cust.user_id = customer_user.id
    await db_session.commit()

    # Tax rule: 18%
    tax = TaxRule(
        organization_id=org.id,
        name="GST 18%",
        rate=Decimal("18.00"),
        is_active=True,
    )
    # Discount rule: Fixed 100 off on min spend 500
    discount = DiscountRule(
        organization_id=org.id,
        name="Flat 100 Off",
        discount_type=DiscountType.FIXED_AMOUNT,
        discount_value=Decimal("100.00"),
        min_purchase_amount=Decimal("500.00"),
        scope=DiscountScope.SUBSCRIPTION,
        max_uses=10,
        times_used=0,
        is_active=True,
    )
    plan = SubscriptionPlan(
        organization_id=org.id,
        name="Monthly Pro Cloud",
        billing_interval=BillingInterval.MONTHLY,
        interval_count=1,
        base_price=Decimal("1000.00"),
        currency="INR",
        min_quantity=1,
        auto_close_on_expiry=True,
        allow_early_close=True,
        allow_pause=True,
        allow_renewal=True,
    )
    product = Product(
        organization_id=org.id,
        name="Cloud ERP Seat",
        product_type=ProductType.SOFTWARE,
        sales_price=Decimal("1000.00"),
        cost_price=Decimal("200.00"),
        is_active=True,
    )
    db_session.add_all([tax, discount, plan, product])
    await db_session.commit()
    for item in [tax, discount, plan, product, cust]:
        await db_session.refresh(item)

    today = date.today()
    # Active subscription due for billing today
    sub = Subscription(
        organization_id=org.id,
        subscription_number=f"SUB-{today.year}-0001",
        customer_id=cust.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=30),
        expiry_date=today + timedelta(days=335),
        next_billing_date=today,
        status=SubscriptionStatus.ACTIVE,
        auto_close_on_expiry=True,
        allow_early_close=True,
        allow_pause=True,
        allow_renewal=True,
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("162.00"),
        discount_amount=Decimal("100.00"),
        total_amount=Decimal("1062.00"),
    )
    db_session.add(sub)
    await db_session.flush()

    line = SubscriptionLine(
        organization_id=org.id,
        subscription_id=sub.id,
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("1000.00"),
        tax_id=tax.id,
        discount_rule_id=discount.id,
        tax_amount=Decimal("162.00"),
        discount_amount=Decimal("100.00"),
        line_total=Decimal("1062.00"),
    )
    db_session.add(line)
    await db_session.commit()
    await db_session.refresh(sub)

    return {
        "org": org,
        "customer": cust,
        "plan": plan,
        "product": product,
        "tax": tax,
        "discount": discount,
        "subscription": sub,
    }


# ==========================================
# 1. Unit & Service Tests
# ==========================================


async def test_create_invoice_for_subscription(db_session: AsyncSession, sample_invoice_setup: dict):
    setup = sample_invoice_setup
    org = setup["org"]
    sub = setup["subscription"]

    invoice = await InvoiceService.create_invoice_for_subscription(
        session=db_session,
        organization_id=org.id,
        subscription_id=sub.id,
    )

    assert invoice.id is not None
    assert invoice.organization_id == org.id
    assert invoice.subscription_id == sub.id
    assert invoice.status == InvoiceStatus.DRAFT
    assert invoice.invoice_number.startswith(f"INV-{date.today().year}-")
    assert invoice.subtotal == Decimal("1000.00")
    assert invoice.discount_amount == Decimal("100.00")
    # Tax on 900 at 18% = 162.00
    assert invoice.tax_amount == Decimal("162.00")
    assert invoice.total_amount == Decimal("1062.00")
    assert invoice.amount_due == Decimal("1062.00")
    assert invoice.amount_paid == Decimal("0.00")
    assert len(invoice.lines) == 1
    assert invoice.lines[0].line_total == Decimal("1062.00")


async def test_cannot_create_invoice_for_inactive_subscription(db_session: AsyncSession, sample_invoice_setup: dict):
    setup = sample_invoice_setup
    org = setup["org"]
    sub = setup["subscription"]
    sub.status = SubscriptionStatus.PAUSED
    await db_session.commit()

    with pytest.raises(InvalidInvoiceStateError, match="Must be Active"):
        await InvoiceService.create_invoice_for_subscription(
            session=db_session,
            organization_id=org.id,
            subscription_id=sub.id,
        )


async def test_confirm_invoice(db_session: AsyncSession, sample_invoice_setup: dict):
    setup = sample_invoice_setup
    org = setup["org"]
    sub = setup["subscription"]

    invoice = await InvoiceService.create_invoice_for_subscription(
        session=db_session,
        organization_id=org.id,
        subscription_id=sub.id,
    )
    assert invoice.status == InvoiceStatus.DRAFT

    confirmed = await InvoiceService.confirm_invoice(
        session=db_session,
        organization_id=org.id,
        invoice_id=invoice.id,
    )
    assert confirmed.status == InvoiceStatus.CONFIRMED

    # Trying to confirm again should raise error
    with pytest.raises(InvalidInvoiceStateError, match="Only 'Draft' invoices can be confirmed"):
        await InvoiceService.confirm_invoice(
            session=db_session,
            organization_id=org.id,
            invoice_id=invoice.id,
        )


async def test_cancel_invoice(db_session: AsyncSession, sample_invoice_setup: dict):
    setup = sample_invoice_setup
    org = setup["org"]
    sub = setup["subscription"]

    invoice = await InvoiceService.create_invoice_for_subscription(
        session=db_session,
        organization_id=org.id,
        subscription_id=sub.id,
    )

    cancelled = await InvoiceService.cancel_invoice(
        session=db_session,
        organization_id=org.id,
        invoice_id=invoice.id,
        reason="Customer requested contract renegotiation",
    )
    assert cancelled.status == InvoiceStatus.CANCELLED
    assert cancelled.amount_due == Decimal("0.00")
    assert "Customer requested contract renegotiation" in cancelled.notes

    # Cannot cancel already cancelled
    with pytest.raises(InvalidInvoiceStateError, match="already cancelled"):
        await InvoiceService.cancel_invoice(
            session=db_session,
            organization_id=org.id,
            invoice_id=invoice.id,
        )


async def test_cannot_cancel_paid_invoice(db_session: AsyncSession, sample_invoice_setup: dict):
    setup = sample_invoice_setup
    org = setup["org"]
    sub = setup["subscription"]

    invoice = await InvoiceService.create_invoice_for_subscription(
        session=db_session,
        organization_id=org.id,
        subscription_id=sub.id,
    )
    invoice.status = InvoiceStatus.PAID
    await db_session.commit()

    with pytest.raises(InvalidInvoiceStateError, match="Paid invoices are immutable"):
        await InvoiceService.cancel_invoice(
            session=db_session,
            organization_id=org.id,
            invoice_id=invoice.id,
        )


# ==========================================
# 2. Automated Billing Sweep Tests
# ==========================================


async def test_billing_sweep_generates_invoice_and_advances_date(db_session: AsyncSession, sample_invoice_setup: dict):
    setup = sample_invoice_setup
    org = setup["org"]
    sub = setup["subscription"]
    today = date.today()

    assert sub.next_billing_date == today
    assert sub.last_billed_date is None

    invoices = await InvoiceService.run_billing_sweep(
        session=db_session,
        as_of_date=today,
        organization_id=org.id,
    )

    assert len(invoices) == 1
    inv = invoices[0]
    assert inv.subscription_id == sub.id
    assert inv.invoice_date == today
    assert inv.status == InvoiceStatus.DRAFT

    # Subscription state advanced
    await db_session.refresh(sub)
    assert sub.last_billed_date == today
    # Advanced by 1 month (handles 31st -> 30th clamp properly)
    assert sub.next_billing_date > today
    assert sub.next_billing_date.month == (today.month % 12 + 1)


async def test_billing_sweep_idempotency_prevents_double_billing(db_session: AsyncSession, sample_invoice_setup: dict):
    setup = sample_invoice_setup
    org = setup["org"]
    sub = setup["subscription"]
    today = date.today()

    # Run 1: Generates invoice
    run1_invoices = await InvoiceService.run_billing_sweep(
        session=db_session,
        as_of_date=today,
        organization_id=org.id,
    )
    assert len(run1_invoices) == 1

    # Run 2 on the same day: Must generate 0 invoices (no double billing!)
    run2_invoices = await InvoiceService.run_billing_sweep(
        session=db_session,
        as_of_date=today,
        organization_id=org.id,
    )
    assert len(run2_invoices) == 0


async def test_billing_sweep_auto_close_on_expiry(db_session: AsyncSession, sample_invoice_setup: dict):
    setup = sample_invoice_setup
    org = setup["org"]
    sub = setup["subscription"]
    today = date.today()

    # Set expiry date to today
    sub.expiry_date = today
    sub.auto_close_on_expiry = True
    await db_session.commit()

    invoices = await InvoiceService.run_billing_sweep(
        session=db_session,
        as_of_date=today,
        organization_id=org.id,
    )
    assert len(invoices) == 1

    await db_session.refresh(sub)
    # Next billing advanced past expiry -> subscription closed automatically
    assert sub.status == SubscriptionStatus.CLOSED


# ==========================================
# 3. REST API Endpoint Tests
# ==========================================


async def test_api_list_and_get_invoices(client: AsyncClient, sample_invoice_setup: dict, seed_data: dict):
    staff_headers = auth_header(seed_data["staff_a"])
    setup = sample_invoice_setup
    sub = setup["subscription"]

    # Generate an invoice via endpoint
    create_res = await client.post(
        f"/api/v1/invoices/from-subscription/{sub.id}",
        headers=staff_headers,
    )
    assert create_res.status_code == 201
    inv_data = create_res.json()
    invoice_id = inv_data["id"]
    assert inv_data["status"] == "draft"

    # List invoices
    list_res = await client.get("/api/v1/invoices", headers=staff_headers)
    assert list_res.status_code == 200
    invoices = list_res.json()
    assert len(invoices) >= 1
    assert any(i["id"] == invoice_id for i in invoices)

    # Get single invoice
    get_res = await client.get(f"/api/v1/invoices/{invoice_id}", headers=staff_headers)
    assert get_res.status_code == 200
    single = get_res.json()
    assert single["id"] == invoice_id
    assert len(single["lines"]) == 1


async def test_api_confirm_and_cancel_invoices(client: AsyncClient, sample_invoice_setup: dict, seed_data: dict):
    staff_headers = auth_header(seed_data["staff_a"])
    setup = sample_invoice_setup
    sub = setup["subscription"]

    # Create invoice
    create_res = await client.post(
        f"/api/v1/invoices/from-subscription/{sub.id}",
        headers=staff_headers,
    )
    inv_id = create_res.json()["id"]

    # Confirm
    conf_res = await client.post(f"/api/v1/invoices/{inv_id}/confirm", headers=staff_headers)
    assert conf_res.status_code == 200
    assert conf_res.json()["status"] == "confirmed"

    # Cancel confirmed invoice
    canc_res = await client.post(
        f"/api/v1/invoices/{inv_id}/cancel",
        json={"reason": "Customer cancellation request"},
        headers=staff_headers,
    )
    assert canc_res.status_code == 200
    assert canc_res.json()["status"] == "cancelled"
    assert "Customer cancellation request" in canc_res.json()["notes"]


async def test_api_customer_portal_isolation(client: AsyncClient, sample_invoice_setup: dict, seed_data: dict):
    customer_headers = auth_header(seed_data["customer_a"])
    staff_headers = auth_header(seed_data["staff_a"])
    setup = sample_invoice_setup
    sub = setup["subscription"]

    create_res = await client.post(
        f"/api/v1/invoices/from-subscription/{sub.id}",
        headers=staff_headers,
    )
    inv_id = create_res.json()["id"]

    # Customer can view their own invoice
    get_res = await client.get(f"/api/v1/invoices/{inv_id}", headers=customer_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == inv_id

    # Customer cannot confirm invoices
    conf_res = await client.post(f"/api/v1/invoices/{inv_id}/confirm", headers=customer_headers)
    assert conf_res.status_code == 403

    # Customer cannot cancel invoices
    canc_res = await client.post(f"/api/v1/invoices/{inv_id}/cancel", headers=customer_headers)
    assert canc_res.status_code == 403

    # Customer cannot trigger billing sweeps
    sweep_res = await client.post("/api/v1/invoices/sweep", headers=customer_headers)
    assert sweep_res.status_code == 403


async def test_api_tenant_isolation(client: AsyncClient, sample_invoice_setup: dict, seed_data: dict):
    staff_a_headers = auth_header(seed_data["staff_a"])
    admin_b_headers = auth_header(seed_data["admin_b"])
    setup = sample_invoice_setup
    sub = setup["subscription"]

    # Create invoice in Tenant Alpha
    create_res = await client.post(
        f"/api/v1/invoices/from-subscription/{sub.id}",
        headers=staff_a_headers,
    )
    inv_id = create_res.json()["id"]

    # Admin from Tenant Beta attempts to access Org A's invoice -> 404
    get_res = await client.get(f"/api/v1/invoices/{inv_id}", headers=admin_b_headers)
    assert get_res.status_code == 404

    # Admin Beta attempts to confirm Org A's invoice -> 404
    conf_res = await client.post(f"/api/v1/invoices/{inv_id}/confirm", headers=admin_b_headers)
    assert conf_res.status_code == 404


async def test_api_trigger_billing_sweep(client: AsyncClient, sample_invoice_setup: dict, seed_data: dict):
    staff_headers = auth_header(seed_data["staff_a"])

    res = await client.post(
        "/api/v1/invoices/sweep",
        json={"as_of_date": date.today().isoformat()},
        headers=staff_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["invoices_generated"] >= 1
    assert Decimal(str(data["total_billed_amount"])) > Decimal("0.00")
    assert len(data["invoice_ids"]) >= 1


# ==========================================
# 4. Celery Worker Task Test
# ==========================================


def test_celery_task_execution():
    with patch("app.workers.billing_tasks._execute_billing_sweep") as mock_exec:
        async def fake_execute(*args, **kwargs):
            return {
                "status": "success",
                "as_of_date": "2026-10-31",
                "invoices_generated": 2,
                "total_billed_amount": "2124.00",
                "invoice_ids": [101, 102],
            }
        mock_exec.side_effect = fake_execute

        result = run_daily_billing_sweep(as_of_date_iso="2026-10-31", organization_id=1)
        assert result["status"] == "success"
        assert result["invoices_generated"] == 2
        assert result["total_billed_amount"] == "2124.00"
        assert result["invoice_ids"] == [101, 102]
