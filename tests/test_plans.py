from datetime import date, timedelta
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import BillingInterval, SubscriptionPlan
from app.services.plan_service import (
    PlanNotAvailableError,
    PlanNotFoundError,
    PlanService,
    QuantityBelowMinimumError,
)
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_admin_create_plans_all_billing_intervals(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]

    # Daily, Weekly, Monthly, Yearly intervals according to Problem Statement
    intervals = [
        ("Daily Trial Pass", "daily", "49.00", 1),
        ("Weekly Sprint License", "weekly", "299.00", 1),
        ("Monthly Business Cloud", "monthly", "999.00", 1),
        ("Enterprise Annual Contract", "yearly", "9999.00", 5),
    ]

    for name, interval, price, min_qty in intervals:
        resp = await client.post(
            "/api/v1/plans",
            json={
                "name": name,
                "description": f"Standard {interval} billing plan",
                "billing_interval": interval,
                "interval_count": 1,
                "base_price": price,
                "currency": "INR",
                "min_quantity": min_qty,
                "auto_close_on_expiry": True,
                "allow_early_close": True,
                "allow_pause": True,
                "allow_renewal": True,
            },
            headers=auth_header(admin),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == name
        assert data["billing_interval"] == interval
        assert Decimal(data["base_price"]) == Decimal(price)
        assert data["min_quantity"] == min_qty
        assert data["auto_close_on_expiry"] is True
        assert data["allow_pause"] is True


@pytest.mark.asyncio
async def test_plan_lifecycle_policies_and_toggles(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]

    # Create a plan with strict policies: closes on expiry, cannot be closed early, cannot be paused
    create_resp = await client.post(
        "/api/v1/plans",
        json={
            "name": "Strict Fixed Contract",
            "billing_interval": "monthly",
            "base_price": "1500.00",
            "auto_close_on_expiry": True,
            "allow_early_close": False,
            "allow_pause": False,
            "allow_renewal": False,
        },
        headers=auth_header(admin),
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["id"]
    assert create_resp.json()["allow_pause"] is False
    assert create_resp.json()["allow_early_close"] is False

    # Admin updates plan to allow early close and pausing
    update_resp = await client.patch(
        f"/api/v1/plans/{plan_id}",
        json={
            "allow_pause": True,
            "allow_early_close": True,
        },
        headers=auth_header(admin),
    )
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["allow_pause"] is True
    assert updated_data["allow_early_close"] is True


@pytest.mark.asyncio
async def test_plan_service_eligibility_validation(db_session: AsyncSession, seed_data: dict):
    org = seed_data["org_a"]
    today = date.today()

    # 1. Plan with minimum quantity of 10
    plan_qty = SubscriptionPlan(
        organization_id=org.id,
        name="Team Bulk Plan",
        billing_interval=BillingInterval.MONTHLY,
        base_price=Decimal("5000.00"),
        min_quantity=10,
        is_active=True,
    )
    db_session.add(plan_qty)

    # 2. Plan with future availability window
    plan_future = SubscriptionPlan(
        organization_id=org.id,
        name="Upcoming Q1 Promotion",
        billing_interval=BillingInterval.YEARLY,
        base_price=Decimal("12000.00"),
        min_quantity=1,
        available_from=today + timedelta(days=10),
        available_until=today + timedelta(days=40),
        is_active=True,
    )
    db_session.add(plan_future)
    await db_session.commit()

    # Test quantity validation: 5 seats should fail (< 10)
    with pytest.raises(QuantityBelowMinimumError):
        PlanService.validate_subscription_eligibility(plan_qty, quantity=5, target_date=today)

    # 10 seats should pass
    PlanService.validate_subscription_eligibility(plan_qty, quantity=10, target_date=today)

    # Test future date availability: today should fail
    with pytest.raises(PlanNotAvailableError):
        PlanService.validate_subscription_eligibility(plan_future, quantity=1, target_date=today)

    # Target date within window should pass
    PlanService.validate_subscription_eligibility(plan_future, quantity=1, target_date=today + timedelta(days=15))


@pytest.mark.asyncio
async def test_staff_can_view_but_not_create_or_update_plans(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]
    staff = seed_data["staff_a"]

    # Admin creates plan
    create_resp = await client.post(
        "/api/v1/plans",
        json={"name": "Staff Viewable Plan", "billing_interval": "monthly", "base_price": "750.00"},
        headers=auth_header(admin),
    )
    plan_id = create_resp.json()["id"]

    # Staff lists plans -> 200 OK
    list_resp = await client.get("/api/v1/plans", headers=auth_header(staff))
    assert list_resp.status_code == 200
    assert any(p["name"] == "Staff Viewable Plan" for p in list_resp.json())

    # Staff gets plan details -> 200 OK
    get_resp = await client.get(f"/api/v1/plans/{plan_id}", headers=auth_header(staff))
    assert get_resp.status_code == 200

    # Staff attempts to create plan -> 403 Forbidden
    post_resp = await client.post(
        "/api/v1/plans",
        json={"name": "Unauthorized Plan", "billing_interval": "daily", "base_price": "10.00"},
        headers=auth_header(staff),
    )
    assert post_resp.status_code == 403

    # Staff attempts to update plan -> 403 Forbidden
    patch_resp = await client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"base_price": "800.00"},
        headers=auth_header(staff),
    )
    assert patch_resp.status_code == 403


@pytest.mark.asyncio
async def test_customer_forbidden_from_plan_management_api(client: AsyncClient, seed_data: dict):
    customer = seed_data["customer_a"]
    resp = await client.get("/api/v1/plans", headers=auth_header(customer))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_tenant_isolation_plans(client: AsyncClient, seed_data: dict):
    admin_a = seed_data["admin_a"]
    admin_b = seed_data["admin_b"]

    # Org A creates a private plan
    plan_a_resp = await client.post(
        "/api/v1/plans",
        json={"name": "Org A Custom Plan", "billing_interval": "yearly", "base_price": "50000.00"},
        headers=auth_header(admin_a),
    )
    plan_a_id = plan_a_resp.json()["id"]

    # Org B lists plans: Org A plan must NOT appear
    list_b = await client.get("/api/v1/plans", headers=auth_header(admin_b))
    assert list_b.status_code == 200
    names = [p["name"] for p in list_b.json()]
    assert "Org A Custom Plan" not in names

    # Org B gets 404 attempting to fetch Org A plan by ID
    get_b = await client.get(f"/api/v1/plans/{plan_a_id}", headers=auth_header(admin_b))
    assert get_b.status_code == 404

    # Org B gets 404 attempting to modify Org A plan
    patch_b = await client.patch(f"/api/v1/plans/{plan_a_id}", json={"base_price": "1.00"}, headers=auth_header(admin_b))
    assert patch_b.status_code == 404


@pytest.mark.asyncio
async def test_plan_filtering_and_archive(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]

    # Create monthly plan
    await client.post(
        "/api/v1/plans",
        json={"name": "Monthly Pro", "billing_interval": "monthly", "base_price": "999.00"},
        headers=auth_header(admin),
    )
    # Create yearly plan
    create_yr = await client.post(
        "/api/v1/plans",
        json={"name": "Yearly Enterprise", "billing_interval": "yearly", "base_price": "9990.00"},
        headers=auth_header(admin),
    )
    yr_plan_id = create_yr.json()["id"]

    # Filter by monthly interval
    filter_resp = await client.get("/api/v1/plans?billing_interval=monthly", headers=auth_header(admin))
    assert filter_resp.status_code == 200
    intervals = [p["billing_interval"] for p in filter_resp.json()]
    assert all(i == "monthly" for i in intervals)

    # Search filter
    search_resp = await client.get("/api/v1/plans?search=Enterprise", headers=auth_header(admin))
    assert search_resp.status_code == 200
    searched = search_resp.json()
    assert len(searched) == 1
    assert searched[0]["name"] == "Yearly Enterprise"

    # Archive yearly plan
    archive_resp = await client.post(f"/api/v1/plans/{yr_plan_id}/archive", headers=auth_header(admin))
    assert archive_resp.status_code == 200
    assert archive_resp.json()["is_active"] is False

    # Active-only list should exclude archived plan
    active_resp = await client.get("/api/v1/plans?is_active=true", headers=auth_header(admin))
    active_ids = [p["id"] for p in active_resp.json()]
    assert yr_plan_id not in active_ids
