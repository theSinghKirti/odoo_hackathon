"""
Demo Data Seeder for Subly Multi-Tenant Subscription Platform.
Populates realistic filler data:
- Staff members and Customer portal users
- Customers (enterprises & startups)
- Products, Variants, and Add-ons across Software, Service, Physical
- Subscription Plans (Monthly, Yearly, Notice periods, Auto-close policies)
- Tax Rules (GST, VAT) and Discount Rules (Annual discount, Startup promo)
- Quotation Templates and Quotations (Draft, Sent, Converted)
- Subscriptions (Active, Paused, Closed) with MRR/ARR and renewal tracking
- Invoices (Paid, Confirmed/Overdue, Draft) and Payments (Razorpay, Bank Transfer)
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.customer import Customer
from app.models.discount import DiscountRule, DiscountScope, DiscountType
from app.models.invoice import Invoice, InvoiceLine, InvoiceStatus
from app.models.organization import Organization
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.plan import BillingInterval, SubscriptionPlan
from app.models.product import Product, ProductType, ProductVariant
from app.models.quotation import Quotation, QuotationLine, QuotationStatus
from app.models.quotation_template import QuotationTemplate, QuotationTemplateLine
from app.models.subscription import Subscription, SubscriptionLine, SubscriptionStatus
from app.models.tax import TaxRule
from app.models.user import User, UserRole
from app.services.password_service import hash_password

logger = logging.getLogger("seed_demo_data")


async def seed_demo_data(session: AsyncSession) -> None:
    # =========================================================================
    # 1. ORG RESOLUTION
    # =========================================================================
    stmt_org = select(Organization).where(Organization.slug == settings.INITIAL_TENANT_SLUG)
    res_org = await session.execute(stmt_org)
    org = res_org.scalars().first()
    if not org:
        org = Organization(
            name=settings.INITIAL_TENANT_NAME,
            slug=settings.INITIAL_TENANT_SLUG,
            is_active=True,
        )
        session.add(org)
        await session.flush()
        logger.info(f"Created reference tenant: {org.name}")

    org_id = org.id

    # =========================================================================
    # 2. STAFF MEMBERS
    # =========================================================================
    staff_data = [
        ("Marcus Vance", "marcus.staff@brightloop.io", "Staff@Brightloop123"),
        ("Sarah Lin", "sarah.sales@brightloop.io", "Sales@Brightloop123"),
    ]
    for full_name, email, pwd in staff_data:
        stmt_u = select(User).where(User.organization_id == org_id, User.email == email.lower())
        res_u = await session.execute(stmt_u)
        if not res_u.scalars().first():
            staff = User(
                organization_id=org_id,
                full_name=full_name,
                email=email.lower(),
                password_hash=hash_password(pwd),
                role=UserRole.STAFF,
                is_active=True,
                is_verified=True,
            )
            session.add(staff)
            logger.info(f"Created staff user: {email}")

    await session.flush()

    # =========================================================================
    # 3. TAX RULES
    # =========================================================================
    taxes_data = [
        ("GST Standard (18%)", Decimal("18.00")),
        ("GST Reduced (5%)", Decimal("5.00")),
        ("Zero Tax Export (0%)", Decimal("0.00")),
        ("EU VAT Standard (20%)", Decimal("20.00")),
    ]
    tax_map = {}
    for name, rate in taxes_data:
        stmt_t = select(TaxRule).where(TaxRule.organization_id == org_id, TaxRule.name == name)
        res_t = await session.execute(stmt_t)
        tax_obj = res_t.scalars().first()
        if not tax_obj:
            tax_obj = TaxRule(
                organization_id=org_id,
                name=name,
                rate=rate,
                is_active=True,
            )
            session.add(tax_obj)
            await session.flush()
            logger.info(f"Created tax rule: {name}")
        tax_map[name] = tax_obj

    # =========================================================================
    # 4. DISCOUNT RULES
    # =========================================================================
    discounts_data = [
        ("Annual Upfront Discount (15%)", DiscountType.PERCENTAGE, Decimal("15.00"), DiscountScope.SUBSCRIPTION, Decimal("0.00")),
        ("Startup Growth Offer (20%)", DiscountType.PERCENTAGE, Decimal("20.00"), DiscountScope.SUBSCRIPTION, Decimal("0.00")),
        ("Volume Enterprise Credit ($500)", DiscountType.FIXED_AMOUNT, Decimal("500.00"), DiscountScope.SUBSCRIPTION, Decimal("2500.00")),
        ("Add-on Trial Promo ($30)", DiscountType.FIXED_AMOUNT, Decimal("30.00"), DiscountScope.PRODUCT, Decimal("50.00")),
    ]
    discount_map = {}
    for name, d_type, d_val, scope, min_p in discounts_data:
        stmt_d = select(DiscountRule).where(DiscountRule.organization_id == org_id, DiscountRule.name == name)
        res_d = await session.execute(stmt_d)
        disc_obj = res_d.scalars().first()
        if not disc_obj:
            disc_obj = DiscountRule(
                organization_id=org_id,
                name=name,
                discount_type=d_type,
                discount_value=d_val,
                scope=scope,
                min_purchase_amount=min_p,
                min_quantity=1,
                start_date=date(2025, 1, 1),
                end_date=date(2027, 12, 31),
                is_active=True,
            )
            session.add(disc_obj)
            await session.flush()
            logger.info(f"Created discount rule: {name}")
        discount_map[name] = disc_obj

    # =========================================================================
    # 5. PRODUCTS & VARIANTS
    # =========================================================================
    products_def = [
        {
            "name": "Subly Core Platform",
            "type": ProductType.SOFTWARE,
            "sales_price": Decimal("49.00"),
            "cost_price": Decimal("10.00"),
            "notes": "Core multitenant recurring billing engine",
            "variants": [
                ("Edition", "Starter Edition", Decimal("0.00"), "SUB-CORE-START"),
                ("Edition", "Growth Edition", Decimal("100.00"), "SUB-CORE-GROWTH"),
                ("Edition", "Enterprise Suite", Decimal("450.00"), "SUB-CORE-ENT"),
            ],
        },
        {
            "name": "AI Predictive Analytics Copilot",
            "type": ProductType.ADDON,
            "sales_price": Decimal("79.00"),
            "cost_price": Decimal("20.00"),
            "notes": "Automated churn forecasting and revenue anomalies",
            "variants": [
                ("Tier", "Standard Copilot", Decimal("0.00"), "ADD-AI-STD"),
                ("Tier", "Real-Time Inference Pro", Decimal("120.00"), "ADD-AI-PRO"),
            ],
        },
        {
            "name": "High-Throughput API Gateway",
            "type": ProductType.SOFTWARE,
            "sales_price": Decimal("99.00"),
            "cost_price": Decimal("15.00"),
            "notes": "Low-latency webhook delivery and rate-limit scaling",
            "variants": [
                ("Bandwidth", "100k Monthly API Calls", Decimal("0.00"), "API-100K"),
                ("Bandwidth", "1M Monthly API Calls", Decimal("200.00"), "API-1M"),
            ],
        },
        {
            "name": "Enterprise Priority SLA Support",
            "type": ProductType.SERVICE,
            "sales_price": Decimal("250.00"),
            "cost_price": Decimal("80.00"),
            "notes": "Dedicated solution architect and guaranteed 15-minute response SLA",
            "variants": [
                ("SLA Level", "8x5 Business Hours", Decimal("0.00"), "SRV-SLA-8X5"),
                ("SLA Level", "24/7 Dedicated Slack Bridge", Decimal("500.00"), "SRV-SLA-247"),
            ],
        },
        {
            "name": "Hardware Security Token (FIDO2)",
            "type": ProductType.PHYSICAL,
            "sales_price": Decimal("45.00"),
            "cost_price": Decimal("20.00"),
            "notes": "Hardware key for biometric compliance and admin MFA enforcement",
            "variants": [
                ("Package", "Single Token", Decimal("0.00"), "HW-KEY-1"),
                ("Package", "Enterprise 5-Pack", Decimal("155.00"), "HW-KEY-5"),
            ],
        },
    ]

    prod_map = {}
    variant_map = {}
    for pdef in products_def:
        stmt_p = select(Product).where(Product.organization_id == org_id, Product.name == pdef["name"])
        res_p = await session.execute(stmt_p)
        prod = res_p.scalars().first()
        if not prod:
            prod = Product(
                organization_id=org_id,
                name=pdef["name"],
                product_type=pdef["type"],
                sales_price=pdef["sales_price"],
                cost_price=pdef["cost_price"],
                notes=pdef["notes"],
                is_active=True,
            )
            session.add(prod)
            await session.flush()
            logger.info(f"Created product: {prod.name}")

            for attr_name, attr_val, extra, sku in pdef["variants"]:
                v = ProductVariant(
                    organization_id=org_id,
                    product_id=prod.id,
                    attribute_name=attr_name,
                    attribute_value=attr_val,
                    price_extra=extra,
                    sku=sku,
                    is_active=True,
                )
                session.add(v)
                await session.flush()
                variant_map[sku] = v
        else:
            # fetch variants
            stmt_v = select(ProductVariant).where(ProductVariant.product_id == prod.id)
            res_v = await session.execute(stmt_v)
            for v in res_v.scalars().all():
                if v.sku:
                    variant_map[v.sku] = v

        prod_map[pdef["name"]] = prod

    # =========================================================================
    # 6. SUBSCRIPTION PLANS
    # =========================================================================
    plans_data = [
        {
            "name": "Pro Growth Monthly",
            "description": "Standard monthly subscription for high-growth tech firms with flexible billing",
            "interval": BillingInterval.MONTHLY,
            "interval_count": 1,
            "price": Decimal("149.00"),
            "min_quantity": 1,
            "auto_close": False,
            "allow_close": True,
            "allow_pause": True,
            "allow_renewal": True,
        },
        {
            "name": "Enterprise Annual Contract",
            "description": "Annual enterprise commitment with custom SLA retainer and dedicated support",
            "interval": BillingInterval.YEARLY,
            "interval_count": 1,
            "price": Decimal("4999.00"),
            "min_quantity": 1,
            "auto_close": False,
            "allow_close": False,
            "allow_pause": True,
            "allow_renewal": True,
        },
        {
            "name": "Starter Tier Monthly",
            "description": "Self-service starter package for early ventures and prototype deployments",
            "interval": BillingInterval.MONTHLY,
            "interval_count": 1,
            "price": Decimal("49.00"),
            "min_quantity": 1,
            "auto_close": True,
            "allow_close": True,
            "allow_pause": True,
            "allow_renewal": True,
        },
    ]

    plan_map = {}
    for pld in plans_data:
        stmt_pl = select(SubscriptionPlan).where(SubscriptionPlan.organization_id == org_id, SubscriptionPlan.name == pld["name"])
        res_pl = await session.execute(stmt_pl)
        plan_obj = res_pl.scalars().first()
        if not plan_obj:
            plan_obj = SubscriptionPlan(
                organization_id=org_id,
                name=pld["name"],
                description=pld["description"],
                billing_interval=pld["interval"],
                interval_count=pld["interval_count"],
                base_price=pld["price"],
                currency="USD",
                min_quantity=pld["min_quantity"],
                auto_close_on_expiry=pld["auto_close"],
                allow_early_close=pld["allow_close"],
                allow_pause=pld["allow_pause"],
                allow_renewal=pld["allow_renewal"],
                is_active=True,
            )
            session.add(plan_obj)
            await session.flush()
            logger.info(f"Created subscription plan: {plan_obj.name}")
        plan_map[pld["name"]] = plan_obj

    # =========================================================================
    # 7. QUOTATION TEMPLATES
    # =========================================================================
    stmt_qt = select(QuotationTemplate).where(QuotationTemplate.organization_id == org_id, QuotationTemplate.name == "Standard SaaS Onboarding Template")
    res_qt = await session.execute(stmt_qt)
    q_tmpl = res_qt.scalars().first()
    if not q_tmpl:
        q_tmpl = QuotationTemplate(
            organization_id=org_id,
            name="Standard SaaS Onboarding Template",
            validity_days=30,
            plan_id=plan_map["Pro Growth Monthly"].id,
            notes="Default sales template for mid-market clients",
        )
        session.add(q_tmpl)
        await session.flush()

        line1 = QuotationTemplateLine(
            organization_id=org_id,
            template_id=q_tmpl.id,
            product_id=prod_map["Subly Core Platform"].id,
            variant_id=variant_map.get("SUB-CORE-GROWTH", None).id if "SUB-CORE-GROWTH" in variant_map else None,
            quantity=1,
            unit_price=Decimal("149.00"),
        )
        line2 = QuotationTemplateLine(
            organization_id=org_id,
            template_id=q_tmpl.id,
            product_id=prod_map["AI Predictive Analytics Copilot"].id,
            variant_id=variant_map.get("ADD-AI-STD", None).id if "ADD-AI-STD" in variant_map else None,
            quantity=1,
            unit_price=Decimal("79.00"),
        )
        session.add_all([line1, line2])
        await session.flush()
        logger.info("Created quotation template and lines")

    # =========================================================================
    # 8. CUSTOMERS & PORTAL USERS
    # =========================================================================
    customers_data = [
        {
            "name": "Acme Cloud Logistics",
            "email": "billing@acmecloud.io",
            "phone": "+1-555-019-2834",
            "address": "742 Evergreen Terrace, Suite 400, Springfield, OR",
            "create_user": True,
            "full_name": "Jordan Bell (Acme)",
        },
        {
            "name": "FinTech Prime Ltd",
            "email": "finance@fintechprime.com",
            "phone": "+44-20-7946-0912",
            "address": "100 Bishopsgate, Level 18, London EC2N 4AG, UK",
            "create_user": True,
            "full_name": "Victoria Sterling (FinTech)",
        },
        {
            "name": "HyperScale Analytics Inc",
            "email": "ops@hyperscale.ai",
            "phone": "+1-415-555-0147",
            "address": "500 Howard Street, San Francisco, CA 94105",
            "create_user": True,
            "full_name": "David Chen (HyperScale)",
        },
        {
            "name": "BlueWave Health Technologies",
            "email": "accounts@bluewave.health",
            "phone": "+1-617-555-0182",
            "address": "125 Cambridge Park Dr, Cambridge, MA 02140",
            "create_user": True,
            "full_name": "Dr. Emily Taylor (BlueWave)",
        },
        {
            "name": "Quantum Leap Robotics",
            "email": "procurement@quantumrobotics.de",
            "phone": "+49-30-2312-5890",
            "address": "Friedrichstraße 68, 10117 Berlin, Germany",
            "create_user": False,
            "full_name": "Klaus Richter",
        },
        {
            "name": "Silverline Media Studios",
            "email": "hello@silverlinemedia.co",
            "phone": "+91-80-4012-3456",
            "address": "Indiranagar 100 Feet Road, Bengaluru, KA 560038",
            "create_user": False,
            "full_name": "Rohan Mehra",
        },
    ]

    cust_map = {}
    for cdata in customers_data:
        stmt_c = select(Customer).where(Customer.organization_id == org_id, Customer.email == cdata["email"].lower())
        res_c = await session.execute(stmt_c)
        cust = res_c.scalars().first()
        if not cust:
            user_id = None
            if cdata["create_user"]:
                stmt_cu = select(User).where(User.organization_id == org_id, User.email == cdata["email"].lower())
                res_cu = await session.execute(stmt_cu)
                cust_user = res_cu.scalars().first()
                if not cust_user:
                    cust_user = User(
                        organization_id=org_id,
                        full_name=cdata["full_name"],
                        email=cdata["email"].lower(),
                        password_hash=hash_password("Customer@1234"),
                        role=UserRole.CUSTOMER,
                        is_active=True,
                        is_verified=True,
                    )
                    session.add(cust_user)
                    await session.flush()
                user_id = cust_user.id

            cust = Customer(
                organization_id=org_id,
                user_id=user_id,
                name=cdata["name"],
                email=cdata["email"].lower(),
                phone=cdata["phone"],
                address=cdata["address"],
                is_active=True,
            )
            session.add(cust)
            await session.flush()
            logger.info(f"Created customer: {cust.name}")
        cust_map[cdata["name"]] = cust

    # =========================================================================
    # 9. QUOTATIONS
    # =========================================================================
    quotes_data = [
        {
            "number": "QT-2026-0001",
            "customer": "Acme Cloud Logistics",
            "plan": "Pro Growth Monthly",
            "status": QuotationStatus.CONVERTED,
            "subtotal": Decimal("228.00"),
            "tax": Decimal("41.04"),
            "discount": Decimal("0.00"),
            "total": Decimal("269.04"),
        },
        {
            "number": "QT-2026-0002",
            "customer": "FinTech Prime Ltd",
            "plan": "Enterprise Annual Contract",
            "status": QuotationStatus.CONVERTED,
            "subtotal": Decimal("4999.00"),
            "tax": Decimal("849.83"),
            "discount": Decimal("749.85"),
            "total": Decimal("5098.98"),
        },
        {
            "number": "QT-2026-0003",
            "customer": "Quantum Leap Robotics",
            "plan": "Pro Growth Monthly",
            "status": QuotationStatus.QUOTATION,
            "subtotal": Decimal("228.00"),
            "tax": Decimal("41.04"),
            "discount": Decimal("0.00"),
            "total": Decimal("269.04"),
        },
        {
            "number": "QT-2026-0004",
            "customer": "Silverline Media Studios",
            "plan": "Starter Tier Monthly",
            "status": QuotationStatus.DRAFT,
            "subtotal": Decimal("49.00"),
            "tax": Decimal("8.82"),
            "discount": Decimal("0.00"),
            "total": Decimal("57.82"),
        },
    ]

    quote_map = {}
    today = date.today()
    for qd in quotes_data:
        stmt_q = select(Quotation).where(Quotation.organization_id == org_id, Quotation.quotation_number == qd["number"])
        res_q = await session.execute(stmt_q)
        q_obj = res_q.scalars().first()
        if not q_obj:
            q_obj = Quotation(
                organization_id=org_id,
                quotation_number=qd["number"],
                customer_id=cust_map[qd["customer"]].id,
                plan_id=plan_map[qd["plan"]].id,
                start_date=today - timedelta(days=45),
                expiry_date=today + timedelta(days=15),
                status=qd["status"],
                subtotal=qd["subtotal"],
                tax_amount=qd["tax"],
                discount_amount=qd["discount"],
                total_amount=qd["total"],
                notes="Standard terms and conditions apply.",
            )
            session.add(q_obj)
            await session.flush()

            # Add quotation line
            q_line = QuotationLine(
                organization_id=org_id,
                quotation_id=q_obj.id,
                product_id=prod_map["Subly Core Platform"].id,
                variant_id=variant_map.get("SUB-CORE-GROWTH", None).id if "SUB-CORE-GROWTH" in variant_map else None,
                quantity=1,
                unit_price=Decimal("149.00"),
                tax_id=tax_map["GST Standard (18%)"].id,
                tax_amount=Decimal("26.82"),
                discount_amount=Decimal("0.00"),
                line_total=Decimal("175.82"),
            )
            session.add(q_line)
            await session.flush()
            logger.info(f"Created quotation: {q_obj.quotation_number}")
        quote_map[qd["number"]] = q_obj

    # =========================================================================
    # 10. SUBSCRIPTIONS & SUBSCRIPTION LINES
    # =========================================================================
    subs_data = [
        {
            "number": "SUB-2026-0001",
            "customer": "Acme Cloud Logistics",
            "plan": "Pro Growth Monthly",
            "quotation": "QT-2026-0001",
            "status": SubscriptionStatus.ACTIVE,
            "start": today - timedelta(days=60),
            "expiry": today + timedelta(days=305),
            "next_billing": today + timedelta(days=1),
            "last_billed": today - timedelta(days=29),
            "subtotal": Decimal("228.00"),
            "tax": Decimal("41.04"),
            "discount": Decimal("0.00"),
            "total": Decimal("269.04"),
        },
        {
            "number": "SUB-2026-0002",
            "customer": "FinTech Prime Ltd",
            "plan": "Enterprise Annual Contract",
            "quotation": "QT-2026-0002",
            "status": SubscriptionStatus.ACTIVE,
            "start": today - timedelta(days=120),
            "expiry": today + timedelta(days=245),
            "next_billing": today + timedelta(days=245),
            "last_billed": today - timedelta(days=120),
            "subtotal": Decimal("4999.00"),
            "tax": Decimal("849.83"),
            "discount": Decimal("749.85"),
            "total": Decimal("5098.98"),
        },
        {
            "number": "SUB-2026-0003",
            "customer": "HyperScale Analytics Inc",
            "plan": "Starter Tier Monthly",
            "quotation": None,
            "status": SubscriptionStatus.PAUSED,
            "start": today - timedelta(days=90),
            "expiry": today + timedelta(days=275),
            "next_billing": today + timedelta(days=15),
            "last_billed": today - timedelta(days=30),
            "subtotal": Decimal("49.00"),
            "tax": Decimal("8.82"),
            "discount": Decimal("0.00"),
            "total": Decimal("57.82"),
        },
        {
            "number": "SUB-2026-0004",
            "customer": "BlueWave Health Technologies",
            "plan": "Pro Growth Monthly",
            "quotation": None,
            "status": SubscriptionStatus.CLOSED,
            "start": today - timedelta(days=365),
            "expiry": today - timedelta(days=5),
            "next_billing": today - timedelta(days=5),
            "last_billed": today - timedelta(days=35),
            "subtotal": Decimal("149.00"),
            "tax": Decimal("26.82"),
            "discount": Decimal("0.00"),
            "total": Decimal("175.82"),
        },
    ]

    sub_map = {}
    for sd in subs_data:
        stmt_s = select(Subscription).where(Subscription.organization_id == org_id, Subscription.subscription_number == sd["number"])
        res_s = await session.execute(stmt_s)
        sub_obj = res_s.scalars().first()
        if not sub_obj:
            sub_obj = Subscription(
                organization_id=org_id,
                subscription_number=sd["number"],
                customer_id=cust_map[sd["customer"]].id,
                plan_id=plan_map[sd["plan"]].id,
                quotation_id=quote_map[sd["quotation"]].id if sd["quotation"] else None,
                start_date=sd["start"],
                expiry_date=sd["expiry"],
                next_billing_date=sd["next_billing"],
                last_billed_date=sd["last_billed"],
                status=sd["status"],
                auto_close_on_expiry=plan_map[sd["plan"]].auto_close_on_expiry,
                allow_early_close=plan_map[sd["plan"]].allow_early_close,
                allow_pause=plan_map[sd["plan"]].allow_pause,
                allow_renewal=plan_map[sd["plan"]].allow_renewal,
                subtotal=sd["subtotal"],
                tax_amount=sd["tax"],
                discount_amount=sd["discount"],
                total_amount=sd["total"],
                notes="Automated lifecycle subscription contract",
            )
            session.add(sub_obj)
            await session.flush()

            # Add subscription line
            s_line = SubscriptionLine(
                organization_id=org_id,
                subscription_id=sub_obj.id,
                product_id=prod_map["Subly Core Platform"].id,
                variant_id=variant_map.get("SUB-CORE-GROWTH", None).id if "SUB-CORE-GROWTH" in variant_map else None,
                quantity=1,
                unit_price=Decimal("149.00"),
                tax_id=tax_map["GST Standard (18%)"].id,
                tax_amount=Decimal("26.82"),
                discount_amount=Decimal("0.00"),
                line_total=Decimal("175.82"),
            )
            session.add(s_line)
            await session.flush()
            logger.info(f"Created subscription: {sub_obj.subscription_number}")
        sub_map[sd["number"]] = sub_obj

    # =========================================================================
    # 11. INVOICES & PAYMENTS
    # =========================================================================
    invoices_data = [
        {
            "number": "INV-2026-0001",
            "customer": "Acme Cloud Logistics",
            "subscription": "SUB-2026-0001",
            "status": InvoiceStatus.PAID,
            "inv_date": today - timedelta(days=60),
            "due_date": today - timedelta(days=45),
            "subtotal": Decimal("228.00"),
            "tax": Decimal("41.04"),
            "discount": Decimal("0.00"),
            "total": Decimal("269.04"),
            "paid": Decimal("269.04"),
            "due": Decimal("0.00"),
            "payment": {
                "method": PaymentMethod.RAZORPAY,
                "amount": Decimal("269.04"),
                "date": today - timedelta(days=59),
                "order_id": "order_mock_001_acme",
                "payment_id": "pay_mock_001_acme",
            },
        },
        {
            "number": "INV-2026-0002",
            "customer": "Acme Cloud Logistics",
            "subscription": "SUB-2026-0001",
            "status": InvoiceStatus.PAID,
            "inv_date": today - timedelta(days=29),
            "due_date": today - timedelta(days=14),
            "subtotal": Decimal("228.00"),
            "tax": Decimal("41.04"),
            "discount": Decimal("0.00"),
            "total": Decimal("269.04"),
            "paid": Decimal("269.04"),
            "due": Decimal("0.00"),
            "payment": {
                "method": PaymentMethod.BANK_TRANSFER,
                "amount": Decimal("269.04"),
                "date": today - timedelta(days=25),
                "order_id": None,
                "payment_id": "WIRE-REF-98120",
            },
        },
        {
            "number": "INV-2026-0003",
            "customer": "FinTech Prime Ltd",
            "subscription": "SUB-2026-0002",
            "status": InvoiceStatus.PAID,
            "inv_date": today - timedelta(days=120),
            "due_date": today - timedelta(days=90),
            "subtotal": Decimal("4999.00"),
            "tax": Decimal("849.83"),
            "discount": Decimal("749.85"),
            "total": Decimal("5098.98"),
            "paid": Decimal("5098.98"),
            "due": Decimal("0.00"),
            "payment": {
                "method": PaymentMethod.BANK_TRANSFER,
                "amount": Decimal("5098.98"),
                "date": today - timedelta(days=115),
                "order_id": None,
                "payment_id": "SWIFT-FT-20260315",
            },
        },
        {
            "number": "INV-2026-0004",
            "customer": "HyperScale Analytics Inc",
            "subscription": "SUB-2026-0003",
            "status": InvoiceStatus.CONFIRMED,
            "inv_date": today - timedelta(days=30),
            "due_date": today - timedelta(days=5),  # Overdue
            "subtotal": Decimal("49.00"),
            "tax": Decimal("8.82"),
            "discount": Decimal("0.00"),
            "total": Decimal("57.82"),
            "paid": Decimal("0.00"),
            "due": Decimal("57.82"),
            "payment": None,
        },
        {
            "number": "INV-2026-0005",
            "customer": "Quantum Leap Robotics",
            "subscription": None,
            "status": InvoiceStatus.DRAFT,
            "inv_date": today - timedelta(days=2),
            "due_date": today + timedelta(days=13),
            "subtotal": Decimal("350.00"),
            "tax": Decimal("63.00"),
            "discount": Decimal("0.00"),
            "total": Decimal("413.00"),
            "paid": Decimal("0.00"),
            "due": Decimal("413.00"),
            "payment": None,
        },
    ]

    for inv_d in invoices_data:
        stmt_i = select(Invoice).where(Invoice.organization_id == org_id, Invoice.invoice_number == inv_d["number"])
        res_i = await session.execute(stmt_i)
        inv_obj = res_i.scalars().first()
        if not inv_obj:
            inv_obj = Invoice(
                organization_id=org_id,
                invoice_number=inv_d["number"],
                subscription_id=sub_map[inv_d["subscription"]].id if inv_d["subscription"] else None,
                customer_id=cust_map[inv_d["customer"]].id,
                invoice_date=inv_d["inv_date"],
                due_date=inv_d["due_date"],
                status=inv_d["status"],
                subtotal=inv_d["subtotal"],
                tax_amount=inv_d["tax"],
                discount_amount=inv_d["discount"],
                total_amount=inv_d["total"],
                amount_paid=inv_d["paid"],
                amount_due=inv_d["due"],
                notes="Net 15 days payment terms.",
            )
            session.add(inv_obj)
            await session.flush()

            # Add invoice line
            inv_line = InvoiceLine(
                organization_id=org_id,
                invoice_id=inv_obj.id,
                product_id=prod_map["Subly Core Platform"].id,
                variant_id=variant_map.get("SUB-CORE-GROWTH", None).id if "SUB-CORE-GROWTH" in variant_map else None,
                description="Subly Core Platform Recurring Usage",
                quantity=1,
                unit_price=inv_d["subtotal"],
                tax_id=tax_map["GST Standard (18%)"].id,
                tax_amount=inv_d["tax"],
                discount_amount=inv_d["discount"],
                line_total=inv_d["total"],
            )
            session.add(inv_line)
            await session.flush()

            if inv_d["payment"]:
                p_info = inv_d["payment"]
                pay_obj = Payment(
                    organization_id=org_id,
                    invoice_id=inv_obj.id,
                    customer_id=cust_map[inv_d["customer"]].id,
                    payment_method=p_info["method"],
                    amount=p_info["amount"],
                    payment_date=p_info["date"],
                    status=PaymentStatus.SUCCEEDED,
                    razorpay_order_id=p_info["order_id"],
                    razorpay_payment_id=p_info["payment_id"],
                    note=f"Payment for {inv_d['number']}",
                )
                session.add(pay_obj)
                await session.flush()

            logger.info(f"Created invoice: {inv_obj.invoice_number}")

    await session.commit()
    logger.info("Successfully seeded demo data for Brightloop Software!")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    async with async_session_factory() as session:
        await seed_demo_data(session)


if __name__ == "__main__":
    asyncio.run(main())
