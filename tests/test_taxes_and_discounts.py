from datetime import date, timedelta
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discount import DiscountRule, DiscountScope, DiscountType
from app.models.tax import TaxRule
from app.services.discount_service import DiscountRuleNotFoundError, DiscountService
from app.services.tax_service import TaxRuleNotFoundError, TaxService
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_admin_create_and_list_tax_rules(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]
    staff = seed_data["staff_a"]
    customer = seed_data["customer_a"]

    # 1. Admin creates GST 18% and VAT 5%
    tax_payloads = [
        {"name": "GST 18%", "rate": "18.00", "is_active": True},
        {"name": "VAT 5%", "rate": "5.00", "is_active": True},
    ]
    created_ids = []
    for payload in tax_payloads:
        resp = await client.post(
            "/api/v1/tax-rules",
            json=payload,
            headers=auth_header(admin),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == payload["name"]
        assert Decimal(data["rate"]) == Decimal(payload["rate"])
        assert data["is_active"] is True
        created_ids.append(data["id"])

    # 2. Staff can list tax rules
    list_resp = await client.get("/api/v1/tax-rules", headers=auth_header(staff))
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) >= 2
    names = [item["name"] for item in items]
    assert "GST 18%" in names
    assert "VAT 5%" in names

    # 3. Customer cannot create tax rules
    forbidden_resp = await client.post(
        "/api/v1/tax-rules",
        json={"name": "Illegal Tax", "rate": "10.00"},
        headers=auth_header(customer),
    )
    assert forbidden_resp.status_code == 403


@pytest.mark.asyncio
async def test_tax_calculation_engine_and_rounding():
    # Direct service and model calculation checks
    tax_18 = TaxRule(id=1, organization_id=1, name="GST 18%", rate=Decimal("18.00"), is_active=True)
    tax_inactive = TaxRule(id=2, organization_id=1, name="Old Tax", rate=Decimal("10.00"), is_active=False)

    # 100 * 18% = 18.00
    assert tax_18.calculate_tax(Decimal("100.00")) == Decimal("18.00")
    # Fractional cents rounding: 100.55 * 18% = 18.099 -> 18.10
    assert tax_18.calculate_tax(Decimal("100.55")) == Decimal("18.10")
    # Zero amount
    assert tax_18.calculate_tax(Decimal("0.00")) == Decimal("0.00")
    # Negative amount
    assert tax_18.calculate_tax(Decimal("-50.00")) == Decimal("0.00")
    # Inactive rule returns 0
    assert tax_inactive.calculate_tax(Decimal("500.00")) == Decimal("0.00")

    # Static helper
    assert TaxService.compute_tax(Decimal("250.00"), Decimal("12.00")) == Decimal("30.00")


@pytest.mark.asyncio
async def test_tax_rule_update_and_archive(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]

    # Create rule
    resp = await client.post(
        "/api/v1/tax-rules",
        json={"name": "Municipal Surcharge", "rate": "2.50", "is_active": True},
        headers=auth_header(admin),
    )
    assert resp.status_code == 201
    rule_id = resp.json()["id"]

    # Update rule
    update_resp = await client.patch(
        f"/api/v1/tax-rules/{rule_id}",
        json={"rate": "3.00", "name": "Municipal Surcharge Revised"},
        headers=auth_header(admin),
    )
    assert update_resp.status_code == 200
    assert Decimal(update_resp.json()["rate"]) == Decimal("3.00")
    assert update_resp.json()["name"] == "Municipal Surcharge Revised"

    # Soft archive
    archive_resp = await client.post(
        f"/api/v1/tax-rules/{rule_id}/archive",
        headers=auth_header(admin),
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_admin_create_fixed_and_percentage_discounts(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]
    staff = seed_data["staff_a"]

    # 1. Percentage discount rule
    pct_resp = await client.post(
        "/api/v1/discount-rules",
        json={
            "name": "Volume SaaS Deal 15% Off",
            "discount_type": "percentage",
            "discount_value": "15.00",
            "min_purchase_amount": "1000.00",
            "min_quantity": 3,
            "scope": "subscription",
            "is_active": True,
        },
        headers=auth_header(admin),
    )
    assert pct_resp.status_code == 201
    pct_data = pct_resp.json()
    assert pct_data["name"] == "Volume SaaS Deal 15% Off"
    assert pct_data["discount_type"] == "percentage"
    assert Decimal(pct_data["discount_value"]) == Decimal("15.00")
    assert Decimal(pct_data["min_purchase_amount"]) == Decimal("1000.00")
    assert pct_data["min_quantity"] == 3

    # 2. Fixed amount discount rule
    fixed_resp = await client.post(
        "/api/v1/discount-rules",
        json={
            "name": "New Year Flat 200 Off",
            "discount_type": "fixed_amount",
            "discount_value": "200.00",
            "min_purchase_amount": "500.00",
            "min_quantity": 1,
            "max_uses": 50,
            "scope": "subscription",
            "is_active": True,
        },
        headers=auth_header(admin),
    )
    assert fixed_resp.status_code == 201
    fixed_data = fixed_resp.json()
    assert fixed_data["discount_type"] == "fixed_amount"
    assert Decimal(fixed_data["discount_value"]) == Decimal("200.00")
    assert fixed_data["max_uses"] == 50
    assert fixed_data["times_used"] == 0

    # 3. Staff can view discount list
    list_resp = await client.get("/api/v1/discount-rules", headers=auth_header(staff))
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) >= 2


@pytest.mark.asyncio
async def test_discount_eligibility_criteria(db_session: AsyncSession, seed_data: dict):
    org = seed_data["org_a"]
    today = date.today()

    # Rule with full triggers: min_purchase=1000, min_qty=2, dates [today-1 to today+7], max_uses=2
    rule = DiscountRule(
        organization_id=org.id,
        name="Strict Summer Promo",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        min_purchase_amount=Decimal("1000.00"),
        min_quantity=2,
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=7),
        max_uses=2,
        times_used=0,
        scope=DiscountScope.SUBSCRIPTION,
        is_active=True,
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    # 1. Fails minimum purchase
    assert rule.is_eligible(amount=Decimal("800.00"), quantity=2, target_date=today) is False

    # 2. Fails minimum quantity
    assert rule.is_eligible(amount=Decimal("1500.00"), quantity=1, target_date=today) is False

    # 3. Fails start date (evaluating earlier date)
    assert rule.is_eligible(
        amount=Decimal("1500.00"), quantity=2, target_date=today - timedelta(days=5)
    ) is False

    # 4. Fails end date (evaluating expired date)
    assert rule.is_eligible(
        amount=Decimal("1500.00"), quantity=2, target_date=today + timedelta(days=10)
    ) is False

    # 5. Passes all conditions
    assert rule.is_eligible(amount=Decimal("1200.00"), quantity=2, target_date=today) is True

    # 6. Usage limit exhaustion
    rule.times_used = 2
    assert rule.is_eligible(amount=Decimal("1200.00"), quantity=2, target_date=today) is False


@pytest.mark.asyncio
async def test_discount_calculation_and_cap():
    # Percentage calculation
    pct_rule = DiscountRule(
        organization_id=1,
        name="25% Off",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("25.00"),
        is_active=True,
    )
    # 800 * 25% = 200.00
    assert pct_rule.calculate_discount(Decimal("800.00")) == Decimal("200.00")

    # Fixed amount calculation cannot exceed base amount
    fixed_rule = DiscountRule(
        organization_id=1,
        name="Big 500 Flat",
        discount_type=DiscountType.FIXED_AMOUNT,
        discount_value=Decimal("500.00"),
        is_active=True,
    )
    # 1000 base -> 500 discount
    assert fixed_rule.calculate_discount(Decimal("1000.00")) == Decimal("500.00")
    # 300 base -> 300 discount (capped, cannot create negative total)
    assert fixed_rule.calculate_discount(Decimal("300.00")) == Decimal("300.00")
    # 0 base -> 0 discount
    assert fixed_rule.calculate_discount(Decimal("0.00")) == Decimal("0.00")


@pytest.mark.asyncio
async def test_evaluate_and_apply_discount_service_with_usage_tracking(
    db_session: AsyncSession,
    seed_data: dict,
):
    org = seed_data["org_a"]

    # Create discount rule
    create_dto = DiscountService.create_discount_rule
    rule = await create_dto(
        session=db_session,
        organization_id=org.id,
        data=type(
            "DTO",
            (),
            {
                "name": "One-Time Special 100 Off",
                "discount_type": DiscountType.FIXED_AMOUNT,
                "discount_value": Decimal("100.00"),
                "min_purchase_amount": Decimal("200.00"),
                "min_quantity": 1,
                "start_date": None,
                "end_date": None,
                "max_uses": 1,
                "scope": DiscountScope.SUBSCRIPTION,
                "product_id": None,
                "is_active": True,
            },
        )(),
    )

    # First application: should succeed and record usage
    applied, amount = await DiscountService.evaluate_and_apply_discount(
        session=db_session,
        organization_id=org.id,
        rule_id=rule.id,
        base_amount=Decimal("350.00"),
        quantity=1,
        record_usage=True,
    )
    assert applied is True
    assert amount == Decimal("100.00")

    # Second application: max_uses reached (times_used=1, max_uses=1), must be rejected
    applied2, amount2 = await DiscountService.evaluate_and_apply_discount(
        session=db_session,
        organization_id=org.id,
        rule_id=rule.id,
        base_amount=Decimal("350.00"),
        quantity=1,
        record_usage=True,
    )
    assert applied2 is False
    assert amount2 == Decimal("0.00")


@pytest.mark.asyncio
async def test_tax_and_discount_tenant_isolation(client: AsyncClient, seed_data: dict):
    admin_a = seed_data["admin_a"]
    admin_b = seed_data["admin_b"]

    # Admin A creates a tax rule
    tax_resp = await client.post(
        "/api/v1/tax-rules",
        json={"name": "Org A Specific Tax", "rate": "14.50", "is_active": True},
        headers=auth_header(admin_a),
    )
    assert tax_resp.status_code == 201
    tax_a_id = tax_resp.json()["id"]

    # Admin B cannot view Org A tax rule (404)
    get_resp = await client.get(
        f"/api/v1/tax-rules/{tax_a_id}",
        headers=auth_header(admin_b),
    )
    assert get_resp.status_code == 404

    # Admin A creates a discount rule
    disc_resp = await client.post(
        "/api/v1/discount-rules",
        json={
            "name": "Org A VIP 30% Off",
            "discount_type": "percentage",
            "discount_value": "30.00",
            "min_purchase_amount": "0.00",
            "min_quantity": 1,
            "scope": "subscription",
            "is_active": True,
        },
        headers=auth_header(admin_a),
    )
    assert disc_resp.status_code == 201
    disc_a_id = disc_resp.json()["id"]

    # Admin B cannot update or archive Org A discount rule (404)
    patch_resp = await client.patch(
        f"/api/v1/discount-rules/{disc_a_id}",
        json={"name": "Hacked Discount"},
        headers=auth_header(admin_b),
    )
    assert patch_resp.status_code == 404
