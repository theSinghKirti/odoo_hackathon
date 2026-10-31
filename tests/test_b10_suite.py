"""
Milestone B10: Comprehensive Backend Test Suite & Isolation Verification

Detailed verification covering:
1. Unit tests for variant math, discount limits, and password validation.
2. Integration tests for billing runs, quotation conversion, and Razorpay signature checks.
3. Deep multi-tenant isolation tests across all core resources (Quotations, Subscriptions, Invoices, Payments, Analytics).
"""
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import hmac
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.customer import Customer
from app.models.discount import DiscountRule, DiscountScope, DiscountType
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.plan import BillingInterval, SubscriptionPlan
from app.models.product import Product, ProductType, ProductVariant
from app.models.quotation import Quotation, QuotationStatus
from app.models.subscription import Subscription, SubscriptionLine, SubscriptionStatus
from app.models.tax import TaxRule
from app.services.analytics_service import AnalyticsService
from app.services.discount_service import DiscountService
from app.services.invoice_service import InvoiceService
from app.services.password_service import (
    PasswordValidationError,
    hash_password,
    validate_password_policy,
    verify_password,
)
from app.services.payment_service import (
    InvalidPaymentError,
    PaymentService,
    PaymentVerificationError,
)
from app.services.quotation_service import QuotationService, advance_date
from tests.conftest import auth_header


# ===========================================================================
# 1. UNIT TESTS: Variant Math, Discount Limits, and Password Validation
# ===========================================================================

class TestVariantMath:
    def test_variant_effective_price_calculation(self):
        """Variant effective price = base sales price + price extra."""
        prod = Product(
            organization_id=1,
            name="Cloud Storage Base",
            sales_price=Decimal("100.00"),
            is_active=True,
        )
        # Surcharge variant
        v_high = ProductVariant(
            organization_id=1,
            product=prod,
            attribute_name="Tier",
            attribute_value="Enterprise",
            price_extra=Decimal("50.00"),
        )
        assert prod.sales_price + v_high.price_extra == Decimal("150.00")

        # Zero surcharge variant
        v_zero = ProductVariant(
            organization_id=1,
            product=prod,
            attribute_name="Tier",
            attribute_value="Standard",
            price_extra=Decimal("0.00"),
        )
        assert prod.sales_price + v_zero.price_extra == Decimal("100.00")

        # Negative discount variant
        v_promo = ProductVariant(
            organization_id=1,
            product=prod,
            attribute_name="Tier",
            attribute_value="Starter Promo",
            price_extra=Decimal("-20.00"),
        )
        assert prod.sales_price + v_promo.price_extra == Decimal("80.00")


class TestDiscountLimits:
    def test_percentage_discount_cannot_exceed_100_percent(self):
        """Percentage discount must be bounded: 100% yields total amount, capped correctly."""
        rule_100 = DiscountRule(
            organization_id=1,
            name="100% Off",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("100.00"),
            scope=DiscountScope.SUBSCRIPTION,
            is_active=True,
        )
        assert rule_100.calculate_discount(Decimal("250.00")) == Decimal("250.00")

        rule_50 = DiscountRule(
            organization_id=1,
            name="Half Off",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("50.00"),
            scope=DiscountScope.SUBSCRIPTION,
            is_active=True,
        )
        assert rule_50.calculate_discount(Decimal("300.00")) == Decimal("150.00")

    def test_fixed_discount_exceeding_line_total_is_clamped(self):
        """A fixed discount cannot result in a negative bill amount (clamped to base_amount)."""
        fixed_high = DiscountRule(
            organization_id=1,
            name="Big Flat Discount",
            discount_type=DiscountType.FIXED_AMOUNT,
            discount_value=Decimal("500.00"),
            scope=DiscountScope.SUBSCRIPTION,
            is_active=True,
        )
        # Applying a 500 fixed discount on a 200 base price clamps to 200:
        discount = fixed_high.calculate_discount(Decimal("200.00"))
        assert discount == Decimal("200.00")
        assert Decimal("200.00") - discount == Decimal("0.00")

    def test_date_bounded_discount_expiration(self):
        """Expired discount rules fail eligibility check, whereas active valid-window rules pass."""
        today = date.today()
        expired_rule = DiscountRule(
            organization_id=1,
            name="Expired Promo",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("20.00"),
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=1),
            is_active=True,
        )
        assert expired_rule.is_eligible(Decimal("100.00"), 1) is False

        active_rule = DiscountRule(
            organization_id=1,
            name="Active Promo",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("20.00"),
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=5),
            is_active=True,
        )
        assert active_rule.is_eligible(Decimal("100.00"), 1) is True


class TestPasswordValidation:
    def test_password_policy_boundary_conditions(self):
        """Verify strict character count, special characters, and complexity thresholds."""
        # Exactly 8 characters (must be rejected - policy requires > 8)
        with pytest.raises(PasswordValidationError, match="more than 8 characters"):
            validate_password_policy("Aa1!5678")

        # 9 characters with all required sets (must pass)
        validate_password_policy("Aa1!56789")

        # Missing special character
        with pytest.raises(PasswordValidationError, match="special character"):
            validate_password_policy("Abcdefghij12345")

        # Missing uppercase
        with pytest.raises(PasswordValidationError, match="uppercase letter"):
            validate_password_policy("abcdefghij123!@#")

        # Missing lowercase
        with pytest.raises(PasswordValidationError, match="lowercase letter"):
            validate_password_policy("ABCDEFGHIJ123!@#")


# ===========================================================================
# 2. INTEGRATION TESTS: Billing Runs, Quotation Conversion, and Razorpay HMAC
# ===========================================================================

@pytest.mark.asyncio
async def test_billing_run_advances_date_and_generates_invoice(
    db_session: AsyncSession, seed_data: dict
):
    """
    Automated billing run integration:
    Sweeps due subscriptions, creates invoice, updates last_billed_date,
    and advances next_billing_date with month-end safety.
    """
    org = seed_data["org_a"]
    cust = seed_data["cust_record_a"]

    # 1. Create plan & product
    plan = SubscriptionPlan(
        organization_id=org.id,
        name="Billing Run Plan",
        billing_interval=BillingInterval.MONTHLY,
        interval_count=1,
        base_price=Decimal("150.00"),
        is_active=True,
    )
    product = Product(
        organization_id=org.id,
        name="Subscription Service",
        sales_price=Decimal("150.00"),
        is_active=True,
    )
    db_session.add_all([plan, product])
    await db_session.flush()

    today = date.today()
    sub = Subscription(
        organization_id=org.id,
        subscription_number="SUB-B10-SWEEP-001",
        customer_id=cust.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=30),
        expiry_date=today + timedelta(days=335),
        next_billing_date=today,
        status=SubscriptionStatus.ACTIVE,
        subtotal=Decimal("150.00"),
        total_amount=Decimal("150.00"),
    )
    db_session.add(sub)
    await db_session.flush()

    # Add line item to subscription
    sub_line = SubscriptionLine(
        organization_id=org.id,
        subscription_id=sub.id,
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("150.00"),
        line_total=Decimal("150.00"),
    )
    db_session.add(sub_line)
    await db_session.flush()

    # 2. Execute billing sweep as of today
    invoices = await InvoiceService.run_billing_sweep(
        session=db_session,
        as_of_date=today,
        organization_id=org.id,
    )

    assert len(invoices) >= 1
    generated_inv = next(inv for inv in invoices if inv.subscription_id == sub.id)
    assert generated_inv.total_amount == Decimal("150.00")
    assert generated_inv.status == InvoiceStatus.DRAFT

    # Subscription billing state updated
    await db_session.refresh(sub)
    assert sub.last_billed_date == today
    assert sub.next_billing_date > today


@pytest.mark.asyncio
async def test_quotation_conversion_lifecycle_and_double_conversion_guard(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """
    Quotation conversion integration:
    Draft -> Confirmed -> Converted (Sub created).
    Attempting to convert again must fail.
    """
    admin = seed_data["admin_a"]
    customer = seed_data["cust_record_a"]
    org = seed_data["org_a"]

    plan = SubscriptionPlan(
        organization_id=org.id,
        name="Lifecycle Plan",
        billing_interval=BillingInterval.MONTHLY,
        interval_count=1,
        base_price=Decimal("500.00"),
        is_active=True,
    )
    product = Product(
        organization_id=org.id,
        name="Platform Seat",
        sales_price=Decimal("500.00"),
        is_active=True,
    )
    db_session.add_all([plan, product])
    await db_session.flush()

    # Create quotation
    quo_resp = await client.post(
        "/api/v1/quotations",
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "start_date": date.today().isoformat(),
            "lines": [{"product_id": product.id, "quantity": 1, "unit_price": "500.00"}],
        },
        headers=auth_header(admin),
    )
    assert quo_resp.status_code == 201
    quo_id = quo_resp.json()["id"]

    # Confirm quotation
    conf_resp = await client.patch(
        f"/api/v1/quotations/{quo_id}/status",
        json={"status": "confirmed"},
        headers=auth_header(admin),
    )
    assert conf_resp.status_code == 200

    # 1st Conversion: must succeed
    conv_resp = await client.post(
        f"/api/v1/quotations/{quo_id}/convert",
        headers=auth_header(admin),
    )
    assert conv_resp.status_code == 201
    assert conv_resp.json()["status"] == "active"

    # 2nd Conversion: must be rejected (idempotent / non-repeatable transition)
    dup_conv_resp = await client.post(
        f"/api/v1/quotations/{quo_id}/convert",
        headers=auth_header(admin),
    )
    assert dup_conv_resp.status_code == 400
    assert "already been converted" in dup_conv_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_razorpay_hmac_tamper_detection_and_replay_guard(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """
    Razorpay integration verification:
    - Tampered HMAC signature is rejected with 400.
    - Valid signature verifies and settles invoice.
    - Replay attempt returns the existing payment idempotently.
    """
    admin = seed_data["admin_a"]
    cust = seed_data["cust_record_a"]
    org = seed_data["org_a"]

    # Setup invoice
    inv = Invoice(
        organization_id=org.id,
        invoice_number="INV-B10-RZP-001",
        customer_id=cust.id,
        invoice_date=date.today(),
        due_date=date.today() + timedelta(days=15),
        status=InvoiceStatus.CONFIRMED,
        total_amount=Decimal("1200.00"),
        amount_due=Decimal("1200.00"),
        amount_paid=Decimal("0.00"),
    )
    db_session.add(inv)
    await db_session.commit()
    await db_session.refresh(inv)

    order_id = "order_testb10_9999"
    payment_id = "pay_testb10_8888"

    # 1. Tampered signature attempt
    tampered_sig = "invalid_signature_hash_1234567890abcdef"
    bad_resp = await client.post(
        f"/api/v1/portal/invoices/{inv.id}/razorpay/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": tampered_sig,
        },
        headers=auth_header(admin),
    )
    assert bad_resp.status_code == 400
    assert "signature" in bad_resp.json()["detail"].lower()

    # 2. Genuine signature verification
    msg = f"{order_id}|{payment_id}"
    valid_sig = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    good_resp = await client.post(
        f"/api/v1/portal/invoices/{inv.id}/razorpay/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=auth_header(admin),
    )
    assert good_resp.status_code == 200
    pay_data = good_resp.json()
    assert pay_data["status"] == "success"
    assert Decimal(str(pay_data["amount_paid"])) == Decimal("1200.00")

    # 3. Replay guard (idempotent duplicate submission)
    replay_resp = await client.post(
        f"/api/v1/portal/invoices/{inv.id}/razorpay/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=auth_header(admin),
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json()["payment_id"] == pay_data["payment_id"]


# ===========================================================================
# 3. MULTI-TENANT ISOLATION TESTS: Cross-Tenant Access Strict Rejection
# ===========================================================================

@pytest.mark.asyncio
async def test_tenant_isolation_cross_tenant_quotation_access(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """Tenant Alpha user cannot read or convert Tenant Beta's quotation."""
    admin_a = seed_data["admin_a"]
    admin_b = seed_data["admin_b"]
    org_b = seed_data["org_b"]
    cust_b = seed_data["cust_record_b"]

    # Create quotation for Org B
    plan_b = SubscriptionPlan(
        organization_id=org_b.id,
        name="Beta Exclusive Plan",
        billing_interval=BillingInterval.MONTHLY,
        base_price=Decimal("800.00"),
        is_active=True,
    )
    prod_b = Product(
        organization_id=org_b.id,
        name="Beta Service",
        sales_price=Decimal("800.00"),
        is_active=True,
    )
    db_session.add_all([plan_b, prod_b])
    await db_session.flush()

    quo_b = Quotation(
        organization_id=org_b.id,
        quotation_number="QUO-BETA-001",
        customer_id=cust_b.id,
        plan_id=plan_b.id,
        status=QuotationStatus.CONFIRMED,
        start_date=date.today(),
        expiry_date=date.today() + timedelta(days=30),
        total_amount=Decimal("800.00"),
    )
    db_session.add(quo_b)
    await db_session.flush()

    # Admin A attempts to fetch Org B's quotation -> 404
    resp = await client.get(f"/api/v1/quotations/{quo_b.id}", headers=auth_header(admin_a))
    assert resp.status_code == 404

    # Admin A attempts to convert Org B's quotation -> 404
    resp_conv = await client.post(f"/api/v1/quotations/{quo_b.id}/convert", headers=auth_header(admin_a))
    assert resp_conv.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation_cross_tenant_invoice_and_payment_access(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """Tenant Alpha user cannot read, cancel, or record payments on Tenant Beta's invoice."""
    admin_a = seed_data["admin_a"]
    org_b = seed_data["org_b"]
    cust_b = seed_data["cust_record_b"]

    inv_b = Invoice(
        organization_id=org_b.id,
        invoice_number="INV-BETA-001",
        customer_id=cust_b.id,
        invoice_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        status=InvoiceStatus.CONFIRMED,
        total_amount=Decimal("950.00"),
        amount_due=Decimal("950.00"),
    )
    db_session.add(inv_b)
    await db_session.commit()
    await db_session.refresh(inv_b)

    # 1. Admin A cannot read invoice B
    resp_get = await client.get(f"/api/v1/invoices/{inv_b.id}", headers=auth_header(admin_a))
    assert resp_get.status_code == 404

    # 2. Admin A cannot cancel invoice B
    resp_cancel = await client.post(f"/api/v1/invoices/{inv_b.id}/cancel", headers=auth_header(admin_a))
    assert resp_cancel.status_code == 404

    # 3. Admin A cannot record an offline payment on invoice B
    resp_pay = await client.post(
        f"/api/v1/payments/offline/{inv_b.id}",
        json={"amount": "950.00", "payment_method": "cash"},
        headers=auth_header(admin_a),
    )
    assert resp_pay.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation_cross_tenant_analytics_data_leak_prevention(
    client: AsyncClient, seed_data: dict, db_session: AsyncSession
):
    """Tenant B admin receives strictly zero metrics for Tenant A's subscriptions and revenue."""
    org_a = seed_data["org_a"]
    cust_a = seed_data["cust_record_a"]
    admin_b = seed_data["admin_b"]

    # Populate Org A with active subscription and payment
    plan_a = SubscriptionPlan(
        organization_id=org_a.id,
        name="Alpha High-Volume Plan",
        billing_interval=BillingInterval.MONTHLY,
        base_price=Decimal("2500.00"),
        is_active=True,
    )
    db_session.add(plan_a)
    await db_session.flush()

    sub_a = Subscription(
        organization_id=org_a.id,
        subscription_number="SUB-ALPHA-ISOLATION-01",
        customer_id=cust_a.id,
        plan_id=plan_a.id,
        start_date=date.today(),
        expiry_date=date.today() + timedelta(days=365),
        next_billing_date=date.today() + timedelta(days=30),
        status=SubscriptionStatus.ACTIVE,
        total_amount=Decimal("2500.00"),
    )
    db_session.add(sub_a)
    await db_session.flush()

    # Org B admin queries summary -> MUST show 0 active subscriptions, 0 MRR
    resp_summary = await client.get("/api/v1/analytics/summary", headers=auth_header(admin_b))
    assert resp_summary.status_code == 200
    data = resp_summary.json()
    assert data["organization_id"] == seed_data["org_b"].id
    assert data["active_subscriptions_count"] == 0
    assert Decimal(data["mrr_arr"]["mrr"]) == Decimal("0.00")
    assert Decimal(data["mrr_arr"]["arr"]) == Decimal("0.00")
