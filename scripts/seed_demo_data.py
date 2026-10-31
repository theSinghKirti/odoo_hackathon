import asyncio
from decimal import Decimal
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.organization import Organization
from app.models.product import Product, ProductType, ProductVariant
from app.models.plan import SubscriptionPlan, BillingInterval
from app.models.tax import TaxRule
from app.models.discount import DiscountRule, DiscountType, DiscountScope


async def seed():
    async with async_session_factory() as session:
        # Get Brightloop tenant
        stmt = select(Organization).where(Organization.slug == "brightloop-software")
        res = await session.execute(stmt)
        org = res.scalars().first()
        if not org:
            print("Please run init_db first.")
            return

        print(f"[*] Seeding data for tenant: {org.name} (ID: {org.id})")

        # 1. Products & Variants (with +560 surcharge from problem statement)
        p_check = await session.execute(select(Product).where(Product.organization_id == org.id))
        if not p_check.scalars().first():
            p1 = Product(
                organization_id=org.id,
                name="BrightSuite Enterprise Core",
                product_type=ProductType.SOFTWARE,
                sales_price=Decimal("1200.00"),
                cost_price=Decimal("400.00"),
                is_active=True,
            )
            session.add(p1)
            await session.flush()

            v1 = ProductVariant(
                organization_id=org.id,
                product_id=p1.id,
                attribute_name="Brand Edition",
                attribute_value="Odoo Enterprise Surcharge",
                price_extra=Decimal("560.00"),  # Surcharge from problem statement
                sku="BS-ODOO-560",
                is_active=True,
            )
            v2 = ProductVariant(
                organization_id=org.id,
                product_id=p1.id,
                attribute_name="Brand Edition",
                attribute_value="Standard Edition",
                price_extra=Decimal("0.00"),
                sku="BS-STD-000",
                is_active=True,
            )
            session.add_all([v1, v2])

            p2 = Product(
                organization_id=org.id,
                name="Priority 24/7 Support",
                product_type=ProductType.SERVICE,
                sales_price=Decimal("299.00"),
                cost_price=Decimal("50.00"),
                is_active=True,
            )
            session.add(p2)
            print("  [+] Created Products & Variant (+560 surcharge)")

        # 2. Subscription Plans
        plan_check = await session.execute(select(SubscriptionPlan).where(SubscriptionPlan.organization_id == org.id))
        if not plan_check.scalars().first():
            plans = [
                SubscriptionPlan(
                    organization_id=org.id,
                    name="Daily Sandbox Pass",
                    description="Daily testing and evaluation pass",
                    billing_interval=BillingInterval.DAILY,
                    interval_count=1,
                    base_price=Decimal("49.00"),
                    currency="INR",
                    min_quantity=1,
                ),
                SubscriptionPlan(
                    organization_id=org.id,
                    name="Weekly Sprint License",
                    description="Weekly billing cycle for agile teams",
                    billing_interval=BillingInterval.WEEKLY,
                    interval_count=1,
                    base_price=Decimal("299.00"),
                    currency="INR",
                    min_quantity=1,
                ),
                SubscriptionPlan(
                    organization_id=org.id,
                    name="Monthly Business Pro",
                    description="Standard monthly recurring subscription",
                    billing_interval=BillingInterval.MONTHLY,
                    interval_count=1,
                    base_price=Decimal("999.00"),
                    currency="INR",
                    min_quantity=1,
                ),
                SubscriptionPlan(
                    organization_id=org.id,
                    name="Enterprise Annual Contract",
                    description="Yearly multi-seat plan",
                    billing_interval=BillingInterval.YEARLY,
                    interval_count=1,
                    base_price=Decimal("9999.00"),
                    currency="INR",
                    min_quantity=5,
                ),
            ]
            session.add_all(plans)
            print("  [+] Created 4 Subscription Plans (Daily, Weekly, Monthly, Yearly)")

        # 3. Tax Rules
        tax_check = await session.execute(select(TaxRule).where(TaxRule.organization_id == org.id))
        if not tax_check.scalars().first():
            t1 = TaxRule(
                organization_id=org.id,
                name="GST 18%",
                rate=Decimal("18.00"),
                is_active=True,
            )
            t2 = TaxRule(
                organization_id=org.id,
                name="VAT 5%",
                rate=Decimal("5.00"),
                is_active=True,
            )
            session.add_all([t1, t2])
            print("  [+] Created Tax Rules (GST 18%, VAT 5%)")

        # 4. Discount Rules
        disc_check = await session.execute(select(DiscountRule).where(DiscountRule.organization_id == org.id))
        if not disc_check.scalars().first():
            d1 = DiscountRule(
                organization_id=org.id,
                name="Volume SaaS Deal 15% Off",
                discount_type=DiscountType.PERCENTAGE,
                discount_value=Decimal("15.00"),
                min_purchase_amount=Decimal("1000.00"),
                min_quantity=3,
                scope=DiscountScope.SUBSCRIPTION,
                is_active=True,
            )
            d2 = DiscountRule(
                organization_id=org.id,
                name="New Year Flat 200 Off",
                discount_type=DiscountType.FIXED_AMOUNT,
                discount_value=Decimal("200.00"),
                min_purchase_amount=Decimal("500.00"),
                min_quantity=1,
                max_uses=50,
                scope=DiscountScope.SUBSCRIPTION,
                is_active=True,
            )
            session.add_all([d1, d2])
            print("  [+] Created Discount Rules (15% Volume, 200 Flat)")

        await session.commit()
        print("[SUCCESS] All sample domain data seeded into dev.db!")


if __name__ == "__main__":
    asyncio.run(seed())
