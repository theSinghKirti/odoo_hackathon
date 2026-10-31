from datetime import date, timedelta
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discount import DiscountRule, DiscountType, DiscountScope
from app.models.plan import BillingInterval, SubscriptionPlan
from app.models.product import Product, ProductType, ProductVariant
from app.models.quotation import Quotation, QuotationStatus
from app.models.subscription import SubscriptionStatus
from app.models.tax import TaxRule
from app.services.quotation_service import QuotationService
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_admin_create_and_list_quotation_template(client: AsyncClient, seed_data: dict, db_session: AsyncSession):
    admin = seed_data["admin_a"]
    org = seed_data["org_a"]

    # 1. Setup Plan & Product
    plan = SubscriptionPlan(
        organization_id=org.id,
        name="Quarterly Pro",
        billing_interval=BillingInterval.MONTHLY,
        interval_count=3,
        base_price=Decimal("1500.00"),
        currency="INR",
        min_quantity=1,
    )
    product = Product(
        organization_id=org.id,
        name="Enterprise Cloud CRM",
        product_type=ProductType.SOFTWARE,
        sales_price=Decimal("1000.00"),
        cost_price=Decimal("300.00"),
        is_active=True,
    )
    db_session.add_all([plan, product])
    await db_session.commit()
    await db_session.refresh(plan)
    await db_session.refresh(product)

    # 2. Admin creates template
    resp = await client.post(
        "/api/v1/quotation-templates",
        json={
            "name": "Standard CRM Package 15D",
            "validity_days": 15,
            "plan_id": plan.id,
            "notes": "Net 15 payment terms apply",
            "lines": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                    "unit_price": "1000.00",
                }
            ],
        },
        headers=auth_header(admin),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Standard CRM Package 15D"
    assert data["validity_days"] == 15
    assert data["plan_id"] == plan.id
    assert len(data["lines"]) == 1
    assert data["lines"][0]["quantity"] == 2

    # 3. List templates
    list_resp = await client.get("/api/v1/quotation-templates", headers=auth_header(admin))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1


@pytest.mark.asyncio
async def test_create_quotation_from_template_and_expiry_calculation(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    admin = seed_data["admin_a"]
    customer = seed_data["cust_record_a"]
    org = seed_data["org_a"]

    # 1. Setup Plan, Product, and Template
    plan = SubscriptionPlan(
        organization_id=org.id,
        name="Annual Growth",
        billing_interval=BillingInterval.YEARLY,
        interval_count=1,
        base_price=Decimal("12000.00"),
        currency="INR",
        min_quantity=1,
    )
    product = Product(
        organization_id=org.id,
        name="Analytics Engine",
        product_type=ProductType.SOFTWARE,
        sales_price=Decimal("500.00"),
        cost_price=Decimal("100.00"),
        is_active=True,
    )
    db_session.add_all([plan, product])
    await db_session.commit()
    await db_session.refresh(plan)
    await db_session.refresh(product)

    tpl_resp = await client.post(
        "/api/v1/quotation-templates",
        json={
            "name": "Quick Growth 20D",
            "validity_days": 20,
            "plan_id": plan.id,
            "lines": [{"product_id": product.id, "quantity": 1, "unit_price": "500.00"}],
        },
        headers=auth_header(admin),
    )
    assert tpl_resp.status_code == 201
    tpl_id = tpl_resp.json()["id"]

    # 2. Create Quotation from Template
    today = date.today()
    quo_resp = await client.post(
        "/api/v1/quotations",
        json={
            "customer_id": customer.id,
            "template_id": tpl_id,
            "start_date": today.isoformat(),
        },
        headers=auth_header(admin),
    )
    assert quo_resp.status_code == 201
    quo_data = quo_resp.json()

    # Number format check
    assert quo_data["quotation_number"].startswith(f"QUO-{today.year}-")
    assert quo_data["customer_id"] == customer.id
    assert quo_data["plan_id"] == plan.id
    assert quo_data["status"] == "draft"

    # Expiry calculation: start_date + 20 days
    expected_expiry = (today + timedelta(days=20)).isoformat()
    assert quo_data["expiry_date"] == expected_expiry

    # Pre-filled lines check
    assert len(quo_data["lines"]) == 1
    assert quo_data["lines"][0]["product_id"] == product.id
    assert Decimal(quo_data["total_amount"]) == Decimal("500.00")


@pytest.mark.asyncio
async def test_quotation_variant_surcharge_tax_and_discount_calculation(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    admin = seed_data["admin_a"]
    customer = seed_data["cust_record_a"]
    org = seed_data["org_a"]

    # 1. Product with Odoo Edition Variant (+560 surcharge)
    product = Product(
        organization_id=org.id,
        name="Custom ERP Suite",
        product_type=ProductType.SOFTWARE,
        sales_price=Decimal("1000.00"),
        cost_price=Decimal("300.00"),
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()

    variant = ProductVariant(
        organization_id=org.id,
        product_id=product.id,
        attribute_name="Brand Edition",
        attribute_value="Odoo Surcharge",
        price_extra=Decimal("560.00"),
        sku="ERP-ODOO-560",
        is_active=True,
    )
    db_session.add(variant)

    # 2. Plan, Tax (18%), and Discount (100 Flat)
    plan = SubscriptionPlan(
        organization_id=org.id,
        name="Monthly ERP",
        billing_interval=BillingInterval.MONTHLY,
        interval_count=1,
        base_price=Decimal("1560.00"),
        currency="INR",
        min_quantity=1,
    )
    tax = TaxRule(
        organization_id=org.id,
        name="GST 18%",
        rate=Decimal("18.00"),
        is_active=True,
    )
    disc = DiscountRule(
        organization_id=org.id,
        name="Welcome 100 Off",
        discount_type=DiscountType.FIXED_AMOUNT,
        discount_value=Decimal("100.00"),
        min_purchase_amount=Decimal("500.00"),
        min_quantity=1,
        scope=DiscountScope.SUBSCRIPTION,
        is_active=True,
    )
    db_session.add_all([plan, tax, disc])
    await db_session.commit()
    for item in [product, variant, plan, tax, disc]:
        await db_session.refresh(item)

    # 3. Create Quotation with variant surcharge, tax, and discount
    # Math:
    # unit_price = 1000 + 560 = 1560.00
    # quantity = 2 -> gross = 3120.00
    # discount = 100.00 -> taxable = 3020.00
    # tax = 3020 * 18% = 543.60
    # total = 3020 + 543.60 = 3563.60
    resp = await client.post(
        "/api/v1/quotations",
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "start_date": date.today().isoformat(),
            "lines": [
                {
                    "product_id": product.id,
                    "variant_id": variant.id,
                    "quantity": 2,
                    "tax_id": tax.id,
                    "discount_rule_id": disc.id,
                }
            ],
        },
        headers=auth_header(admin),
    )
    assert resp.status_code == 201
    data = resp.json()

    line = data["lines"][0]
    assert Decimal(line["unit_price"]) == Decimal("1560.00")
    assert Decimal(line["discount_amount"]) == Decimal("100.00")
    assert Decimal(line["tax_amount"]) == Decimal("543.60")
    assert Decimal(line["line_total"]) == Decimal("3563.60")

    assert Decimal(data["subtotal"]) == Decimal("3120.00")
    assert Decimal(data["discount_amount"]) == Decimal("100.00")
    assert Decimal(data["tax_amount"]) == Decimal("543.60")
    assert Decimal(data["total_amount"]) == Decimal("3563.60")


@pytest.mark.asyncio
async def test_atomic_conversion_to_subscription(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    admin = seed_data["admin_a"]
    customer = seed_data["cust_record_a"]
    org = seed_data["org_a"]

    # 1. Setup Plan (monthly interval)
    plan = SubscriptionPlan(
        organization_id=org.id,
        name="Monthly Cloud Team",
        billing_interval=BillingInterval.MONTHLY,
        interval_count=1,
        base_price=Decimal("1200.00"),
        currency="INR",
        min_quantity=1,
        auto_close_on_expiry=True,
        allow_pause=True,
    )
    p_core = Product(
        organization_id=org.id,
        name="Core SaaS Seat",
        product_type=ProductType.SOFTWARE,
        sales_price=Decimal("1000.00"),
        cost_price=Decimal("200.00"),
        is_active=True,
    )
    p_addon = Product(
        organization_id=org.id,
        name="Extra Storage 50GB",
        product_type=ProductType.ADDON,
        sales_price=Decimal("200.00"),
        cost_price=Decimal("50.00"),
        is_active=True,
    )
    db_session.add_all([plan, p_core, p_addon])
    await db_session.commit()
    for item in [plan, p_core, p_addon]:
        await db_session.refresh(item)

    # 2. Create Quotation with core seat and addon
    start_dt = date.today()
    quo_resp = await client.post(
        "/api/v1/quotations",
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "start_date": start_dt.isoformat(),
            "lines": [
                {"product_id": p_core.id, "quantity": 1, "unit_price": "1000.00"},
                {"product_id": p_addon.id, "quantity": 1, "unit_price": "200.00"},
            ],
        },
        headers=auth_header(admin),
    )
    assert quo_resp.status_code == 201
    quo_id = quo_resp.json()["id"]

    # 3. Transition to Confirmed
    status_resp = await client.patch(
        f"/api/v1/quotations/{quo_id}/status",
        json={"status": "confirmed"},
        headers=auth_header(admin),
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "confirmed"

    # 4. Trigger Atomic Conversion
    conv_resp = await client.post(
        f"/api/v1/quotations/{quo_id}/convert",
        headers=auth_header(admin),
    )
    assert conv_resp.status_code == 201
    sub_data = conv_resp.json()

    # Subscription properties verification
    assert sub_data["subscription_number"].startswith(f"SUB-{start_dt.year}-")
    assert sub_data["customer_id"] == customer.id
    assert sub_data["plan_id"] == plan.id
    assert sub_data["quotation_id"] == quo_id
    assert sub_data["status"] == "active"
    assert sub_data["auto_close_on_expiry"] is True
    assert sub_data["allow_pause"] is True

    # Next billing date computed (+1 month from start date with month-end clamping)
    from app.services.quotation_service import advance_date
    expected_next_billing = advance_date(start_dt, BillingInterval.MONTHLY, 1)
    assert sub_data["next_billing_date"] == expected_next_billing.isoformat()

    # Lines deep-copied with addon flag
    lines = sub_data["lines"]
    assert len(lines) == 2
    addon_line = next(l for l in lines if l["product_id"] == p_addon.id)
    assert addon_line["is_addon"] is True

    # 5. Verify Quotation is now marked CONVERTED
    check_quo = await client.get(f"/api/v1/quotations/{quo_id}", headers=auth_header(admin))
    assert check_quo.json()["status"] == "converted"

    # 6. Attempting to convert again must fail
    dup_resp = await client.post(
        f"/api/v1/quotations/{quo_id}/convert",
        headers=auth_header(admin),
    )
    assert dup_resp.status_code == 400


@pytest.mark.asyncio
async def test_conversion_enforces_plan_min_quantity(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    admin = seed_data["admin_a"]
    customer = seed_data["cust_record_a"]
    org = seed_data["org_a"]

    # Enterprise plan requiring minimum 5 seats
    plan = SubscriptionPlan(
        organization_id=org.id,
        name="Enterprise Multi-Seat",
        billing_interval=BillingInterval.MONTHLY,
        interval_count=1,
        base_price=Decimal("5000.00"),
        currency="INR",
        min_quantity=5,
    )
    product = Product(
        organization_id=org.id,
        name="Enterprise License",
        product_type=ProductType.SOFTWARE,
        sales_price=Decimal("1000.00"),
        cost_price=Decimal("200.00"),
        is_active=True,
    )
    db_session.add_all([plan, product])
    await db_session.commit()
    await db_session.refresh(plan)
    await db_session.refresh(product)

    # Create quote with only 2 seats
    quo_resp = await client.post(
        "/api/v1/quotations",
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "start_date": date.today().isoformat(),
            "lines": [{"product_id": product.id, "quantity": 2, "unit_price": "1000.00"}],
        },
        headers=auth_header(admin),
    )
    assert quo_resp.status_code == 201
    quo_id = quo_resp.json()["id"]

    # Conversion must fail because 2 < 5
    conv_resp = await client.post(
        f"/api/v1/quotations/{quo_id}/convert",
        headers=auth_header(admin),
    )
    assert conv_resp.status_code == 400
    assert "minimum requirement" in conv_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_quotation_tenant_isolation(client: AsyncClient, seed_data: dict, db_session: AsyncSession):
    admin_a = seed_data["admin_a"]
    admin_b = seed_data["admin_b"]
    customer_a = seed_data["cust_record_a"]
    org_a = seed_data["org_a"]

    # Plan & Product for Org A
    plan = SubscriptionPlan(
        organization_id=org_a.id,
        name="Org A Exclusive Plan",
        billing_interval=BillingInterval.MONTHLY,
        interval_count=1,
        base_price=Decimal("999.00"),
        currency="INR",
        min_quantity=1,
    )
    product = Product(
        organization_id=org_a.id,
        name="Org A Confidential App",
        product_type=ProductType.SOFTWARE,
        sales_price=Decimal("500.00"),
        cost_price=Decimal("100.00"),
        is_active=True,
    )
    db_session.add_all([plan, product])
    await db_session.commit()
    await db_session.refresh(plan)
    await db_session.refresh(product)

    # Admin A creates quotation
    quo_resp = await client.post(
        "/api/v1/quotations",
        json={
            "customer_id": customer_a.id,
            "plan_id": plan.id,
            "lines": [{"product_id": product.id, "quantity": 1, "unit_price": "500.00"}],
        },
        headers=auth_header(admin_a),
    )
    assert quo_resp.status_code == 201
    quo_id = quo_resp.json()["id"]

    # Admin B cannot view Org A quote
    get_resp = await client.get(f"/api/v1/quotations/{quo_id}", headers=auth_header(admin_b))
    assert get_resp.status_code == 404

    # Admin B cannot convert Org A quote
    conv_resp = await client.post(f"/api/v1/quotations/{quo_id}/convert", headers=auth_header(admin_b))
    assert conv_resp.status_code == 404
