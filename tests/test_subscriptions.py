from datetime import date, timedelta
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.plan import BillingInterval, SubscriptionPlan
from app.models.product import Product, ProductType
from app.models.subscription import Subscription, SubscriptionLine, SubscriptionStatus
from tests.conftest import auth_header


@pytest.fixture
async def sample_subscription_setup(db_session: AsyncSession, seed_data: dict):
    org = seed_data["org_a"]
    cust = seed_data["cust_record_a"]
    customer_user = seed_data["customer_a"]

    # Link customer_a user to cust_record_a for portal testing
    cust.user_id = customer_user.id
    await db_session.commit()

    # Plan with all toggles enabled
    plan_flexible = SubscriptionPlan(
        organization_id=org.id,
        name="Flexible Cloud Pro",
        billing_interval=BillingInterval.MONTHLY,
        interval_count=1,
        base_price=Decimal("999.00"),
        currency="INR",
        min_quantity=1,
        auto_close_on_expiry=True,
        allow_early_close=True,
        allow_pause=True,
        allow_renewal=True,
    )
    # Plan with strict policies
    plan_strict = SubscriptionPlan(
        organization_id=org.id,
        name="Strict Lock-In Plan",
        billing_interval=BillingInterval.YEARLY,
        interval_count=1,
        base_price=Decimal("9999.00"),
        currency="INR",
        min_quantity=1,
        auto_close_on_expiry=True,
        allow_early_close=False,  # Early close prohibited
        allow_pause=False,        # Pause prohibited
        allow_renewal=False,      # Renewal prohibited
    )
    product = Product(
        organization_id=org.id,
        name="Business SaaS Core",
        product_type=ProductType.SOFTWARE,
        sales_price=Decimal("999.00"),
        cost_price=Decimal("150.00"),
        is_active=True,
    )
    db_session.add_all([plan_flexible, plan_strict, product])
    await db_session.commit()
    for item in [plan_flexible, plan_strict, product, cust]:
        await db_session.refresh(item)

    today = date.today()

    # Sub 1: Flexible
    sub1 = Subscription(
        organization_id=org.id,
        subscription_number=f"SUB-{today.year}-0001",
        customer_id=cust.id,
        plan_id=plan_flexible.id,
        start_date=today,
        expiry_date=today + timedelta(days=365),
        next_billing_date=today + timedelta(days=30),
        status=SubscriptionStatus.ACTIVE,
        auto_close_on_expiry=True,
        allow_early_close=True,
        allow_pause=True,
        allow_renewal=True,
        subtotal=Decimal("999.00"),
        total_amount=Decimal("999.00"),
    )
    # Sub 2: Strict
    sub2 = Subscription(
        organization_id=org.id,
        subscription_number=f"SUB-{today.year}-0002",
        customer_id=cust.id,
        plan_id=plan_strict.id,
        start_date=today,
        expiry_date=today + timedelta(days=365),
        next_billing_date=today + timedelta(days=30),
        status=SubscriptionStatus.ACTIVE,
        auto_close_on_expiry=True,
        allow_early_close=False,
        allow_pause=False,
        allow_renewal=False,
        subtotal=Decimal("9999.00"),
        total_amount=Decimal("9999.00"),
    )
    db_session.add_all([sub1, sub2])
    await db_session.flush()

    line1 = SubscriptionLine(
        organization_id=org.id,
        subscription_id=sub1.id,
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("999.00"),
        line_total=Decimal("999.00"),
    )
    line2 = SubscriptionLine(
        organization_id=org.id,
        subscription_id=sub2.id,
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("9999.00"),
        line_total=Decimal("9999.00"),
    )
    db_session.add_all([line1, line2])
    await db_session.commit()
    await db_session.refresh(sub1)
    await db_session.refresh(sub2)

    return {
        "sub_flexible": sub1,
        "sub_strict": sub2,
        "cust": cust,
        "plan_flexible": plan_flexible,
        "plan_strict": plan_strict,
    }


@pytest.mark.asyncio
async def test_pause_and_resume_subscription_lifecycle(
    client: AsyncClient, seed_data: dict, sample_subscription_setup: dict
):
    admin = seed_data["admin_a"]
    sub = sample_subscription_setup["sub_flexible"]

    # 1. Pause active subscription
    pause_resp = await client.post(
        f"/api/v1/subscriptions/{sub.id}/pause",
        headers=auth_header(admin),
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    # 2. Cannot pause an already paused subscription
    dup_pause = await client.post(
        f"/api/v1/subscriptions/{sub.id}/pause",
        headers=auth_header(admin),
    )
    assert dup_pause.status_code == 400

    # 3. Resume paused subscription
    resume_resp = await client.post(
        f"/api/v1/subscriptions/{sub.id}/resume",
        headers=auth_header(admin),
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_pause_forbidden_by_strict_plan_policy(
    client: AsyncClient, seed_data: dict, sample_subscription_setup: dict
):
    admin = seed_data["admin_a"]
    sub_strict = sample_subscription_setup["sub_strict"]

    # Attempting to pause subscription with allow_pause = False must fail
    resp = await client.post(
        f"/api/v1/subscriptions/{sub_strict.id}/pause",
        headers=auth_header(admin),
    )
    assert resp.status_code == 400
    assert "does not permit pausing" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_early_close_policy_enforcement(
    client: AsyncClient, seed_data: dict, sample_subscription_setup: dict
):
    admin = seed_data["admin_a"]
    sub_strict = sample_subscription_setup["sub_strict"]
    sub_flex = sample_subscription_setup["sub_flexible"]

    # 1. Strict subscription (allow_early_close = False) must reject early termination
    strict_close_resp = await client.post(
        f"/api/v1/subscriptions/{sub_strict.id}/close",
        json={"reason": "Customer wants early exit"},
        headers=auth_header(admin),
    )
    assert strict_close_resp.status_code == 400
    assert "prohibits early termination" in strict_close_resp.json()["detail"]

    # 2. Flexible subscription (allow_early_close = True) closes cleanly
    flex_close_resp = await client.post(
        f"/api/v1/subscriptions/{sub_flex.id}/close",
        json={"reason": "Mutual agreement early exit"},
        headers=auth_header(admin),
    )
    assert flex_close_resp.status_code == 200
    data = flex_close_resp.json()
    assert data["status"] == "closed"
    assert "Mutual agreement early exit" in data["notes"]

    # 3. Closed subscription cannot be paused or resumed
    bad_pause = await client.post(
        f"/api/v1/subscriptions/{sub_flex.id}/pause",
        headers=auth_header(admin),
    )
    assert bad_pause.status_code == 400

    bad_resume = await client.post(
        f"/api/v1/subscriptions/{sub_flex.id}/resume",
        headers=auth_header(admin),
    )
    assert bad_resume.status_code == 400


@pytest.mark.asyncio
async def test_renew_subscription_policy(
    client: AsyncClient, seed_data: dict, sample_subscription_setup: dict
):
    admin = seed_data["admin_a"]
    sub_strict = sample_subscription_setup["sub_strict"]
    sub_flex = sample_subscription_setup["sub_flexible"]

    # 1. Strict subscription (allow_renewal = False) must reject renewal
    strict_renew_resp = await client.post(
        f"/api/v1/subscriptions/{sub_strict.id}/renew",
        headers=auth_header(admin),
    )
    assert strict_renew_resp.status_code == 400
    assert "prohibits renewals" in strict_renew_resp.json()["detail"]

    # 2. Flexible subscription (allow_renewal = True) extends expiry
    initial_expiry = date.fromisoformat(sub_flex.expiry_date.isoformat())
    renew_resp = await client.post(
        f"/api/v1/subscriptions/{sub_flex.id}/renew",
        headers=auth_header(admin),
    )
    assert renew_resp.status_code == 200
    new_expiry = date.fromisoformat(renew_resp.json()["expiry_date"])
    assert new_expiry > initial_expiry
    assert renew_resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_customer_portal_subscription_access(
    client: AsyncClient, seed_data: dict, sample_subscription_setup: dict
):
    customer = seed_data["customer_a"]
    sub_flex = sample_subscription_setup["sub_flexible"]

    # 1. Customer can view their own subscription
    resp = await client.get(
        f"/api/v1/subscriptions/{sub_flex.id}",
        headers=auth_header(customer),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == sub_flex.id

    # 2. Customer can pause their own subscription if policy permits
    pause_resp = await client.post(
        f"/api/v1/subscriptions/{sub_flex.id}/pause",
        headers=auth_header(customer),
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    # 3. Customer can resume their own subscription
    resume_resp = await client.post(
        f"/api/v1/subscriptions/{sub_flex.id}/resume",
        headers=auth_header(customer),
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_subscription_tenant_isolation(
    client: AsyncClient, seed_data: dict, sample_subscription_setup: dict
):
    admin_b = seed_data["admin_b"]
    sub_a = sample_subscription_setup["sub_flexible"]

    # Admin B cannot view Org A subscription
    get_resp = await client.get(
        f"/api/v1/subscriptions/{sub_a.id}",
        headers=auth_header(admin_b),
    )
    assert get_resp.status_code == 404

    # Admin B cannot pause Org A subscription
    pause_resp = await client.post(
        f"/api/v1/subscriptions/{sub_a.id}/pause",
        headers=auth_header(admin_b),
    )
    assert pause_resp.status_code == 404
