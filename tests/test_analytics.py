"""
B9 Analytics tests — AnalyticsService + API endpoint coverage.

Tests cover:
  - Active subscription count (empty, single, multi)
  - MRR/ARR normalization for all four billing intervals
  - Revenue collection (all-time and date-windowed)
  - Overdue invoice detection
  - Full summary endpoint
  - Multi-tenant isolation (org_b cannot see org_a data)
  - RBAC: customers cannot access analytics endpoints
"""
import itertools
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.plan import BillingInterval, SubscriptionPlan
from app.models.subscription import Subscription, SubscriptionStatus
from app.services.analytics_service import AnalyticsService
from tests.conftest import auth_header

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)

# Thread-safe unique counter for subscription numbers (avoids UNIQUE violations)
_sub_counter = itertools.count(1)


def _next_sub_number() -> str:
    return f"SUB-TEST-{next(_sub_counter):06d}"


async def _create_plan(
    db: AsyncSession,
    org_id: int,
    interval: BillingInterval,
    price: str = "100.00",
) -> SubscriptionPlan:
    """Create and flush a minimal SubscriptionPlan."""
    plan = SubscriptionPlan(
        organization_id=org_id,
        name=f"Plan-{interval.value}-{next(_sub_counter)}",
        billing_interval=interval,
        base_price=Decimal(price),
        is_active=True,
    )
    db.add(plan)
    await db.flush()
    return plan


async def _create_active_subscription(
    db: AsyncSession,
    org_id: int,
    customer_id: int,
    plan: SubscriptionPlan,
    total_amount: str = "100.00",
) -> Subscription:
    """Create and flush an ACTIVE subscription."""
    sub = Subscription(
        organization_id=org_id,
        subscription_number=_next_sub_number(),
        customer_id=customer_id,
        plan_id=plan.id,
        start_date=TODAY,
        expiry_date=TODAY + timedelta(days=365),
        next_billing_date=TOMORROW,
        status=SubscriptionStatus.ACTIVE,
        total_amount=Decimal(total_amount),
    )
    db.add(sub)
    await db.flush()
    return sub


async def _create_invoice(
    db: AsyncSession,
    org_id: int,
    customer_id: int,
    subscription_id: int,
    invoice_status: InvoiceStatus = InvoiceStatus.CONFIRMED,
    due_date: date = None,
    total: str = "200.00",
    amount_due: str = "200.00",
) -> Invoice:
    """Create and flush an Invoice."""
    if due_date is None:
        due_date = YESTERDAY  # overdue by default
    inv = Invoice(
        organization_id=org_id,
        invoice_number=f"INV-TEST-{next(_sub_counter):06d}",
        customer_id=customer_id,
        subscription_id=subscription_id,
        invoice_date=TODAY,
        due_date=due_date,
        status=invoice_status,
        total_amount=Decimal(total),
        amount_due=Decimal(amount_due),
    )
    db.add(inv)
    await db.flush()
    return inv


async def _create_payment(
    db: AsyncSession,
    org_id: int,
    invoice_id: int,
    customer_id: int,
    amount: str = "100.00",
    payment_date: date = None,
    pay_status: PaymentStatus = PaymentStatus.SUCCEEDED,
) -> Payment:
    """Create and flush a Payment."""
    if payment_date is None:
        payment_date = TODAY
    pay = Payment(
        organization_id=org_id,
        invoice_id=invoice_id,
        customer_id=customer_id,
        payment_method=PaymentMethod.CASH,
        amount=Decimal(amount),
        payment_date=payment_date,
        status=pay_status,
    )
    db.add(pay)
    await db.flush()
    return pay


# ---------------------------------------------------------------------------
# Service tests: Active Subscription Count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_count_empty(db_session: AsyncSession, seed_data: dict):
    """Organization with no subscriptions returns 0."""
    org_a = seed_data["org_a"]
    count = await AnalyticsService.get_active_subscriptions_count(
        db_session, org_a.id
    )
    assert count == 0


@pytest.mark.asyncio
async def test_active_count_single(db_session: AsyncSession, seed_data: dict):
    """One ACTIVE subscription is counted."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    await _create_active_subscription(db_session, org_a.id, cust.id, plan)
    await db_session.flush()

    count = await AnalyticsService.get_active_subscriptions_count(
        db_session, org_a.id
    )
    assert count == 1


@pytest.mark.asyncio
async def test_active_count_excludes_non_active(
    db_session: AsyncSession, seed_data: dict
):
    """CLOSED and PAUSED subscriptions are not counted as active."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    sub = await _create_active_subscription(db_session, org_a.id, cust.id, plan)

    # Flip to closed
    sub.status = SubscriptionStatus.CLOSED
    await db_session.flush()

    count = await AnalyticsService.get_active_subscriptions_count(
        db_session, org_a.id
    )
    assert count == 0


# ---------------------------------------------------------------------------
# Service tests: MRR / ARR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mrr_arr_no_subscriptions(db_session: AsyncSession, seed_data: dict):
    """MRR/ARR is 0 when there are no active subscriptions."""
    org_a = seed_data["org_a"]
    result = await AnalyticsService.get_mrr_arr(db_session, org_a.id)
    assert result.mrr == Decimal("0.00")
    assert result.arr == Decimal("0.00")


@pytest.mark.asyncio
async def test_mrr_monthly_interval(db_session: AsyncSession, seed_data: dict):
    """Monthly subscription total = MRR face value."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    await _create_active_subscription(
        db_session, org_a.id, cust.id, plan, total_amount="500.00"
    )
    await db_session.flush()

    result = await AnalyticsService.get_mrr_arr(db_session, org_a.id)
    assert result.monthly_contribution == Decimal("500.00")
    assert result.mrr == Decimal("500.00")
    assert result.arr == Decimal("6000.00")


@pytest.mark.asyncio
async def test_mrr_yearly_interval(db_session: AsyncSession, seed_data: dict):
    """Yearly subscription total is divided by 12 for MRR."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.YEARLY)
    await _create_active_subscription(
        db_session, org_a.id, cust.id, plan, total_amount="1200.00"
    )
    await db_session.flush()

    result = await AnalyticsService.get_mrr_arr(db_session, org_a.id)
    # 1200 / 12 = 100.00
    assert result.yearly_contribution == Decimal("100.00")
    assert result.mrr == Decimal("100.00")


@pytest.mark.asyncio
async def test_mrr_daily_interval(db_session: AsyncSession, seed_data: dict):
    """Daily subscription total is multiplied by 30 for MRR."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.DAILY)
    await _create_active_subscription(
        db_session, org_a.id, cust.id, plan, total_amount="10.00"
    )
    await db_session.flush()

    result = await AnalyticsService.get_mrr_arr(db_session, org_a.id)
    # 10 * 30 = 300
    assert result.daily_contribution == Decimal("300.00")
    assert result.mrr == Decimal("300.00")


@pytest.mark.asyncio
async def test_mrr_weekly_interval(db_session: AsyncSession, seed_data: dict):
    """Weekly subscription total is multiplied by 4.33 for MRR."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.WEEKLY)
    await _create_active_subscription(
        db_session, org_a.id, cust.id, plan, total_amount="100.00"
    )
    await db_session.flush()

    result = await AnalyticsService.get_mrr_arr(db_session, org_a.id)
    # 100 * 4.33 = 433.00
    assert result.weekly_contribution == Decimal("433.00")
    assert result.mrr == Decimal("433.00")


@pytest.mark.asyncio
async def test_mrr_mixed_intervals(db_session: AsyncSession, seed_data: dict):
    """MRR sums correctly across multiple billing intervals."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]

    monthly_plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    yearly_plan = await _create_plan(db_session, org_a.id, BillingInterval.YEARLY)

    await _create_active_subscription(
        db_session, org_a.id, cust.id, monthly_plan, total_amount="200.00"
    )
    await _create_active_subscription(
        db_session, org_a.id, cust.id, yearly_plan, total_amount="1200.00"
    )
    await db_session.flush()

    result = await AnalyticsService.get_mrr_arr(db_session, org_a.id)
    # 200 (monthly) + 100 (yearly/12) = 300
    assert result.monthly_contribution == Decimal("200.00")
    assert result.yearly_contribution == Decimal("100.00")
    assert result.mrr == Decimal("300.00")
    assert result.arr == Decimal("3600.00")


# ---------------------------------------------------------------------------
# Service tests: Revenue Collected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revenue_collected_empty(db_session: AsyncSession, seed_data: dict):
    """No payments returns 0.00."""
    org_a = seed_data["org_a"]
    result = await AnalyticsService.get_revenue_collected(db_session, org_a.id)
    assert result == Decimal("0.00")


@pytest.mark.asyncio
async def test_revenue_collected_sums_succeeded(
    db_session: AsyncSession, seed_data: dict
):
    """Only SUCCEEDED payments are counted."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    sub = await _create_active_subscription(db_session, org_a.id, cust.id, plan)
    inv = await _create_invoice(
        db_session, org_a.id, cust.id, sub.id, total="500.00", amount_due="500.00"
    )
    # Succeeded payment
    await _create_payment(db_session, org_a.id, inv.id, cust.id, amount="300.00")
    # Failed payment — should NOT be counted
    await _create_payment(
        db_session,
        org_a.id,
        inv.id,
        cust.id,
        amount="200.00",
        pay_status=PaymentStatus.FAILED,
    )
    await db_session.flush()

    total = await AnalyticsService.get_revenue_collected(db_session, org_a.id)
    assert total == Decimal("300.00")


@pytest.mark.asyncio
async def test_revenue_collected_date_window(
    db_session: AsyncSession, seed_data: dict
):
    """Date filter correctly narrows the revenue window."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    sub = await _create_active_subscription(db_session, org_a.id, cust.id, plan)
    inv = await _create_invoice(
        db_session, org_a.id, cust.id, sub.id, total="600.00", amount_due="600.00"
    )
    past = TODAY - timedelta(days=10)
    await _create_payment(
        db_session, org_a.id, inv.id, cust.id, amount="100.00", payment_date=past
    )
    await _create_payment(
        db_session, org_a.id, inv.id, cust.id, amount="200.00", payment_date=TODAY
    )
    await db_session.flush()

    # Only today's payment
    total = await AnalyticsService.get_revenue_collected(
        db_session, org_a.id, start_date=TODAY, end_date=TODAY
    )
    assert total == Decimal("200.00")

    # All-time
    total_all = await AnalyticsService.get_revenue_collected(db_session, org_a.id)
    assert total_all == Decimal("300.00")


# ---------------------------------------------------------------------------
# Service tests: Overdue Invoices
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overdue_invoices_empty(db_session: AsyncSession, seed_data: dict):
    """No invoices returns count=0, total_amount_due=0."""
    org_a = seed_data["org_a"]
    result = await AnalyticsService.get_overdue_invoices(db_session, org_a.id)
    assert result.count == 0
    assert result.total_amount_due == Decimal("0.00")


@pytest.mark.asyncio
async def test_overdue_invoices_detects_overdue(
    db_session: AsyncSession, seed_data: dict
):
    """Confirmed invoice with past due_date is flagged as overdue."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    sub = await _create_active_subscription(db_session, org_a.id, cust.id, plan)
    # Overdue: due yesterday, still confirmed
    await _create_invoice(
        db_session,
        org_a.id,
        cust.id,
        sub.id,
        invoice_status=InvoiceStatus.CONFIRMED,
        due_date=YESTERDAY,
        amount_due="300.00",
    )
    await db_session.flush()

    result = await AnalyticsService.get_overdue_invoices(db_session, org_a.id)
    assert result.count == 1
    assert result.total_amount_due == Decimal("300.00")


@pytest.mark.asyncio
async def test_overdue_invoices_excludes_paid_and_draft(
    db_session: AsyncSession, seed_data: dict
):
    """PAID and DRAFT invoices are excluded from overdue count."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    sub = await _create_active_subscription(db_session, org_a.id, cust.id, plan)

    # Draft invoice past due
    await _create_invoice(
        db_session,
        org_a.id,
        cust.id,
        sub.id,
        invoice_status=InvoiceStatus.DRAFT,
        due_date=YESTERDAY,
    )
    # Paid invoice past due
    await _create_invoice(
        db_session,
        org_a.id,
        cust.id,
        sub.id,
        invoice_status=InvoiceStatus.PAID,
        due_date=YESTERDAY,
    )
    # Confirmed invoice NOT yet due (tomorrow)
    await _create_invoice(
        db_session,
        org_a.id,
        cust.id,
        sub.id,
        invoice_status=InvoiceStatus.CONFIRMED,
        due_date=TOMORROW,
    )
    await db_session.flush()

    result = await AnalyticsService.get_overdue_invoices(db_session, org_a.id)
    assert result.count == 0


# ---------------------------------------------------------------------------
# Service tests: Full Summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_summary_returns_all_metrics(
    db_session: AsyncSession, seed_data: dict
):
    """get_summary aggregates all four KPI sections."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    sub = await _create_active_subscription(
        db_session, org_a.id, cust.id, plan, total_amount="300.00"
    )
    inv = await _create_invoice(
        db_session,
        org_a.id,
        cust.id,
        sub.id,
        invoice_status=InvoiceStatus.CONFIRMED,
        due_date=YESTERDAY,
        total="300.00",
        amount_due="300.00",
    )
    await _create_payment(
        db_session, org_a.id, inv.id, cust.id, amount="150.00"
    )
    await db_session.flush()

    summary = await AnalyticsService.get_summary(db_session, org_a.id)

    assert summary.organization_id == org_a.id
    assert summary.active_subscriptions_count == 1
    assert summary.mrr_arr.mrr == Decimal("300.00")
    assert summary.mrr_arr.arr == Decimal("3600.00")
    assert summary.revenue_collected == Decimal("150.00")
    assert summary.overdue_invoices.count == 1


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_analytics_summary_admin(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """Admin can access /analytics/summary."""
    admin_a = seed_data["admin_a"]
    response = await client.get(
        "/api/v1/analytics/summary",
        headers=auth_header(admin_a),
    )
    assert response.status_code == 200
    data = response.json()
    assert "active_subscriptions_count" in data
    assert "mrr_arr" in data
    assert "revenue_collected" in data
    assert "overdue_invoices" in data


@pytest.mark.asyncio
async def test_api_analytics_summary_staff(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """Staff can access /analytics/summary."""
    staff_a = seed_data["staff_a"]
    response = await client.get(
        "/api/v1/analytics/summary",
        headers=auth_header(staff_a),
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_analytics_customer_denied(
    client: AsyncClient, seed_data: dict
):
    """Customer role is denied access to all analytics endpoints."""
    customer_a = seed_data["customer_a"]
    headers = auth_header(customer_a)

    for path in [
        "/api/v1/analytics/summary",
        "/api/v1/analytics/mrr-arr",
        "/api/v1/analytics/revenue",
        "/api/v1/analytics/invoices/overdue",
        "/api/v1/analytics/subscriptions/active-count",
    ]:
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 403, f"Expected 403 for {path}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_api_analytics_mrr_arr(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """MRR/ARR endpoint returns correct normalization."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    admin_a = seed_data["admin_a"]

    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    await _create_active_subscription(
        db_session, org_a.id, cust.id, plan, total_amount="400.00"
    )
    await db_session.flush()

    resp = await client.get(
        "/api/v1/analytics/mrr-arr", headers=auth_header(admin_a)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mrr"] == "400.00"
    assert data["arr"] == "4800.00"


@pytest.mark.asyncio
async def test_api_analytics_revenue_date_filter(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """Revenue endpoint respects start_date/end_date query params."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    admin_a = seed_data["admin_a"]

    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    sub = await _create_active_subscription(db_session, org_a.id, cust.id, plan)
    inv = await _create_invoice(
        db_session, org_a.id, cust.id, sub.id, total="500.00", amount_due="500.00"
    )
    await _create_payment(
        db_session,
        org_a.id,
        inv.id,
        cust.id,
        amount="250.00",
        payment_date=TODAY - timedelta(days=5),
    )
    await _create_payment(
        db_session, org_a.id, inv.id, cust.id, amount="250.00", payment_date=TODAY
    )
    await db_session.flush()

    resp = await client.get(
        "/api/v1/analytics/revenue",
        headers=auth_header(admin_a),
        params={"start_date": str(TODAY), "end_date": str(TODAY)},
    )
    assert resp.status_code == 200
    assert resp.json()["revenue_collected"] == "250.00"


@pytest.mark.asyncio
async def test_api_analytics_overdue(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """Overdue endpoint returns correct count and total."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    admin_a = seed_data["admin_a"]

    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    sub = await _create_active_subscription(db_session, org_a.id, cust.id, plan)
    await _create_invoice(
        db_session,
        org_a.id,
        cust.id,
        sub.id,
        invoice_status=InvoiceStatus.CONFIRMED,
        due_date=YESTERDAY,
        total="150.00",
        amount_due="150.00",
    )
    await db_session.flush()

    resp = await client.get(
        "/api/v1/analytics/invoices/overdue", headers=auth_header(admin_a)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["total_amount_due"] == "150.00"


@pytest.mark.asyncio
async def test_api_analytics_active_count(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """active-count endpoint returns correct integer."""
    org_a = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    admin_a = seed_data["admin_a"]

    plan = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    await _create_active_subscription(db_session, org_a.id, cust.id, plan)
    await db_session.flush()

    resp = await client.get(
        "/api/v1/analytics/subscriptions/active-count",
        headers=auth_header(admin_a),
    )
    assert resp.status_code == 200
    assert resp.json()["active_subscriptions_count"] == 1


# ---------------------------------------------------------------------------
# Multi-tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analytics_tenant_isolation(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """Org B admin cannot see Org A's subscriptions in analytics."""
    org_a = seed_data["org_a"]
    cust_a = seed_data["cust_record_a"]
    admin_b = seed_data["admin_b"]

    # Create 3 active subscriptions for Org A
    plan_a = await _create_plan(db_session, org_a.id, BillingInterval.MONTHLY)
    for _ in range(3):
        await _create_active_subscription(
            db_session, org_a.id, cust_a.id, plan_a, total_amount="100.00"
        )
    await db_session.flush()

    # Org B admin queries — should see 0, not 3
    resp = await client.get(
        "/api/v1/analytics/subscriptions/active-count",
        headers=auth_header(admin_b),
    )
    assert resp.status_code == 200
    assert resp.json()["active_subscriptions_count"] == 0
