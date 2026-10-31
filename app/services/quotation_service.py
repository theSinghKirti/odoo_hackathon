import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.discount import DiscountRule
from app.models.plan import BillingInterval, SubscriptionPlan
from app.models.product import Product, ProductType, ProductVariant
from app.models.quotation import Quotation, QuotationLine, QuotationStatus
from app.models.quotation_template import QuotationTemplate, QuotationTemplateLine
from app.models.subscription import Subscription, SubscriptionLine, SubscriptionStatus
from app.models.tax import TaxRule
from app.schemas.quotation import QuotationCreate, QuotationLineCreate, QuotationUpdate
from app.schemas.quotation_template import QuotationTemplateCreate, QuotationTemplateUpdate
from app.services.plan_service import PlanService, PlanNotFoundError


class QuotationServiceError(Exception):
    """Base exception for quotation service errors."""
    pass


class QuotationNotFoundError(QuotationServiceError):
    pass


class QuotationTemplateNotFoundError(QuotationServiceError):
    pass


class CustomerNotFoundError(QuotationServiceError):
    pass


class ProductOrVariantNotFoundError(QuotationServiceError):
    pass


class InvalidQuotationStateError(QuotationServiceError):
    pass


def advance_date(base_date: date, interval: BillingInterval, interval_count: int = 1) -> date:
    """Advances a date according to billing intervals handling leap years and month boundaries."""
    if interval == BillingInterval.DAILY:
        return base_date + timedelta(days=interval_count)
    elif interval == BillingInterval.WEEKLY:
        return base_date + timedelta(weeks=interval_count)
    elif interval == BillingInterval.MONTHLY:
        new_year = base_date.year + (base_date.month + interval_count - 1) // 12
        new_month = (base_date.month + interval_count - 1) % 12 + 1
        _, max_days = calendar.monthrange(new_year, new_month)
        new_day = min(base_date.day, max_days)
        return date(new_year, new_month, new_day)
    elif interval == BillingInterval.YEARLY:
        new_year = base_date.year + interval_count
        new_month = base_date.month
        _, max_days = calendar.monthrange(new_year, new_month)
        new_day = min(base_date.day, max_days)
        return date(new_year, new_month, new_day)
    return base_date


class QuotationTemplateService:
    @staticmethod
    async def create_template(
        session: AsyncSession,
        organization_id: int,
        data: QuotationTemplateCreate,
    ) -> QuotationTemplate:
        # Validate plan
        await PlanService.get_plan(session, organization_id=organization_id, plan_id=data.plan_id)

        template = QuotationTemplate(
            organization_id=organization_id,
            name=data.name.strip(),
            validity_days=data.validity_days,
            plan_id=data.plan_id,
            notes=data.notes,
        )
        session.add(template)
        await session.flush()

        for line_in in data.lines:
            t_line = QuotationTemplateLine(
                organization_id=organization_id,
                template_id=template.id,
                product_id=line_in.product_id,
                variant_id=line_in.variant_id,
                quantity=line_in.quantity,
                unit_price=line_in.unit_price,
            )
            session.add(t_line)

        await session.commit()
        return await QuotationTemplateService.get_template(session, organization_id, template.id)

    @staticmethod
    async def get_template(
        session: AsyncSession,
        organization_id: int,
        template_id: int,
    ) -> QuotationTemplate:
        stmt = (
            select(QuotationTemplate)
            .options(
                selectinload(QuotationTemplate.lines),
                selectinload(QuotationTemplate.plan),
            )
            .where(
                and_(
                    QuotationTemplate.id == template_id,
                    QuotationTemplate.organization_id == organization_id,
                )
            )
        )
        res = await session.execute(stmt)
        tpl = res.scalars().first()
        if not tpl:
            raise QuotationTemplateNotFoundError(f"Quotation template {template_id} not found.")
        return tpl

    @staticmethod
    async def list_templates(
        session: AsyncSession,
        organization_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[QuotationTemplate]:
        stmt = (
            select(QuotationTemplate)
            .options(
                selectinload(QuotationTemplate.lines),
                selectinload(QuotationTemplate.plan),
            )
            .where(QuotationTemplate.organization_id == organization_id)
            .order_by(QuotationTemplate.id.desc())
            .offset(skip)
            .limit(limit)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_template(
        session: AsyncSession,
        organization_id: int,
        template_id: int,
        data: QuotationTemplateUpdate,
    ) -> QuotationTemplate:
        tpl = await QuotationTemplateService.get_template(session, organization_id, template_id)

        if data.name is not None:
            tpl.name = data.name.strip()
        if data.validity_days is not None:
            tpl.validity_days = data.validity_days
        if data.plan_id is not None:
            await PlanService.get_plan(session, organization_id=organization_id, plan_id=data.plan_id)
            tpl.plan_id = data.plan_id
        if data.notes is not None:
            tpl.notes = data.notes

        if data.lines is not None:
            # Replace existing lines
            for old_line in list(tpl.lines):
                await session.delete(old_line)
            await session.flush()

            for line_in in data.lines:
                new_line = QuotationTemplateLine(
                    organization_id=organization_id,
                    template_id=tpl.id,
                    product_id=line_in.product_id,
                    variant_id=line_in.variant_id,
                    quantity=line_in.quantity,
                    unit_price=line_in.unit_price,
                )
                session.add(new_line)

        await session.commit()
        return await QuotationTemplateService.get_template(session, organization_id, tpl.id)

    @staticmethod
    async def delete_template(
        session: AsyncSession,
        organization_id: int,
        template_id: int,
    ) -> None:
        tpl = await QuotationTemplateService.get_template(session, organization_id, template_id)
        await session.delete(tpl)
        await session.commit()


class QuotationService:
    @staticmethod
    async def _generate_quotation_number(session: AsyncSession, organization_id: int) -> str:
        year = date.today().year
        stmt = select(func.count(Quotation.id)).where(Quotation.organization_id == organization_id)
        res = await session.execute(stmt)
        count = res.scalar() or 0
        return f"QUO-{year}-{count + 1:04d}"

    @staticmethod
    async def _generate_subscription_number(session: AsyncSession, organization_id: int) -> str:
        year = date.today().year
        stmt = select(func.count(Subscription.id)).where(Subscription.organization_id == organization_id)
        res = await session.execute(stmt)
        count = res.scalar() or 0
        return f"SUB-{year}-{count + 1:04d}"

    @staticmethod
    async def _calculate_line(
        session: AsyncSession,
        organization_id: int,
        line_in: QuotationLineCreate,
        target_date: date,
    ) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        """
        Calculates line totals: (effective_unit_price, tax_amount, discount_amount, line_total).
        Applies product variant surcharge, discount rule eligibility, and tax rate.
        """
        # 1. Fetch Product
        p_stmt = select(Product).where(
            and_(Product.id == line_in.product_id, Product.organization_id == organization_id)
        )
        p_res = await session.execute(p_stmt)
        product = p_res.scalars().first()
        if not product:
            raise ProductOrVariantNotFoundError(f"Product {line_in.product_id} not found in this organization.")

        # 2. Compute effective unit price
        if line_in.unit_price is not None:
            unit_price = line_in.unit_price
        else:
            base_price = product.sales_price
            price_extra = Decimal("0.00")
            if line_in.variant_id:
                v_stmt = select(ProductVariant).where(
                    and_(
                        ProductVariant.id == line_in.variant_id,
                        ProductVariant.product_id == product.id,
                        ProductVariant.organization_id == organization_id,
                    )
                )
                v_res = await session.execute(v_stmt)
                variant = v_res.scalars().first()
                if not variant:
                    raise ProductOrVariantNotFoundError(f"Variant {line_in.variant_id} not found for product {product.id}.")
                price_extra = variant.price_extra
            unit_price = base_price + price_extra

        qty = line_in.quantity
        gross_amount = unit_price * Decimal(qty)

        # 3. Discount calculation
        discount_amount = Decimal("0.00")
        if line_in.discount_rule_id:
            d_stmt = select(DiscountRule).where(
                and_(DiscountRule.id == line_in.discount_rule_id, DiscountRule.organization_id == organization_id)
            )
            d_res = await session.execute(d_stmt)
            disc = d_res.scalars().first()
            if disc and disc.is_eligible(
                amount=gross_amount,
                quantity=qty,
                target_date=target_date,
                target_product_id=product.id,
            ):
                discount_amount = disc.calculate_discount(gross_amount)

        taxable_amount = max(Decimal("0.00"), gross_amount - discount_amount)

        # 4. Tax calculation
        tax_amount = Decimal("0.00")
        if line_in.tax_id:
            t_stmt = select(TaxRule).where(
                and_(TaxRule.id == line_in.tax_id, TaxRule.organization_id == organization_id)
            )
            t_res = await session.execute(t_stmt)
            tax_rule = t_res.scalars().first()
            if tax_rule:
                tax_amount = tax_rule.calculate_tax(taxable_amount)

        line_total = taxable_amount + tax_amount
        return unit_price, tax_amount, discount_amount, line_total

    @staticmethod
    async def create_quotation(
        session: AsyncSession,
        organization_id: int,
        data: QuotationCreate,
    ) -> Quotation:
        # Validate Customer
        c_stmt = select(Customer).where(
            and_(Customer.id == data.customer_id, Customer.organization_id == organization_id)
        )
        c_res = await session.execute(c_stmt)
        customer = c_res.scalars().first()
        if not customer:
            raise CustomerNotFoundError(f"Customer {data.customer_id} not found in this organization.")

        # Resolve Template if provided
        template = None
        if data.template_id:
            template = await QuotationTemplateService.get_template(session, organization_id, data.template_id)

        plan_id = data.plan_id or (template.plan_id if template else None)
        if not plan_id:
            raise QuotationServiceError("Plan ID is required when no template is specified.")

        plan = await PlanService.get_plan(session, organization_id=organization_id, plan_id=plan_id)

        start_date = data.start_date or date.today()
        validity_days = template.validity_days if template else 30
        expiry_date = data.expiry_date or (start_date + timedelta(days=validity_days))

        quo_number = await QuotationService._generate_quotation_number(session, organization_id)

        quotation = Quotation(
            organization_id=organization_id,
            quotation_number=quo_number,
            customer_id=customer.id,
            plan_id=plan.id,
            template_id=template.id if template else None,
            start_date=start_date,
            expiry_date=expiry_date,
            payment_terms=data.payment_terms or (template.notes if template else None),
            status=QuotationStatus.DRAFT,
            notes=data.notes,
        )
        session.add(quotation)
        await session.flush()

        # Prepare lines: either provided or prefilled from template
        raw_lines = data.lines
        if raw_lines is None and template:
            raw_lines = [
                QuotationLineCreate(
                    product_id=tl.product_id,
                    variant_id=tl.variant_id,
                    quantity=tl.quantity,
                    unit_price=tl.unit_price if tl.unit_price > Decimal("0.00") else None,
                )
                for tl in template.lines
            ]
        elif raw_lines is None:
            raw_lines = []

        total_subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_discount = Decimal("0.00")
        total_amount = Decimal("0.00")

        for line_in in raw_lines:
            unit_price, tax_amt, disc_amt, line_tot = await QuotationService._calculate_line(
                session, organization_id, line_in, start_date
            )
            q_line = QuotationLine(
                organization_id=organization_id,
                quotation_id=quotation.id,
                product_id=line_in.product_id,
                variant_id=line_in.variant_id,
                quantity=line_in.quantity,
                unit_price=unit_price,
                tax_id=line_in.tax_id,
                discount_rule_id=line_in.discount_rule_id,
                tax_amount=tax_amt,
                discount_amount=disc_amt,
                line_total=line_tot,
            )
            session.add(q_line)

            total_subtotal += (unit_price * Decimal(line_in.quantity))
            total_tax += tax_amt
            total_discount += disc_amt
            total_amount += line_tot

        quotation.subtotal = total_subtotal
        quotation.tax_amount = total_tax
        quotation.discount_amount = total_discount
        quotation.total_amount = total_amount

        await session.commit()
        return await QuotationService.get_quotation(session, organization_id, quotation.id)

    @staticmethod
    async def get_quotation(
        session: AsyncSession,
        organization_id: int,
        quotation_id: int,
    ) -> Quotation:
        stmt = (
            select(Quotation)
            .options(
                selectinload(Quotation.lines).selectinload(QuotationLine.product),
                selectinload(Quotation.lines).selectinload(QuotationLine.variant),
                selectinload(Quotation.customer),
                selectinload(Quotation.plan),
                selectinload(Quotation.template),
            )
            .where(
                and_(
                    Quotation.id == quotation_id,
                    Quotation.organization_id == organization_id,
                )
            )
        )
        res = await session.execute(stmt)
        quo = res.scalars().first()
        if not quo:
            raise QuotationNotFoundError(f"Quotation {quotation_id} not found in this organization.")
        return quo

    @staticmethod
    async def list_quotations(
        session: AsyncSession,
        organization_id: int,
        customer_id: Optional[int] = None,
        status: Optional[QuotationStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Quotation]:
        filters = [Quotation.organization_id == organization_id]
        if customer_id is not None:
            filters.append(Quotation.customer_id == customer_id)
        if status is not None:
            filters.append(Quotation.status == status)

        stmt = (
            select(Quotation)
            .options(
                selectinload(Quotation.lines),
                selectinload(Quotation.customer),
                selectinload(Quotation.plan),
            )
            .where(and_(*filters))
            .order_by(Quotation.id.desc())
            .offset(skip)
            .limit(limit)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_quotation_status(
        session: AsyncSession,
        organization_id: int,
        quotation_id: int,
        new_status: QuotationStatus,
    ) -> Quotation:
        quo = await QuotationService.get_quotation(session, organization_id, quotation_id)

        # Transition validation
        if quo.status == QuotationStatus.CONVERTED:
            raise InvalidQuotationStateError("Cannot alter quotation that is already converted to a subscription.")
        if quo.status == QuotationStatus.CANCELLED:
            raise InvalidQuotationStateError("Cannot alter quotation that is cancelled.")

        quo.status = new_status
        await session.commit()
        return await QuotationService.get_quotation(session, organization_id, quo.id)

    @staticmethod
    async def convert_quotation_to_subscription(
        session: AsyncSession,
        organization_id: int,
        quotation_id: int,
    ) -> Subscription:
        """
        ATOMIC CONVERSION SERVICE:
        Converts a Confirmed/Quotation quote into a live Subscription in one database transaction.
        1. Validates quote state and plan eligibility.
        2. Calculates next_billing_date according to plan interval.
        3. Copies quotation lines to subscription lines.
        4. Copies plan policy toggles to the subscription snapshot.
        5. Marks quotation as CONVERTED.
        6. Commits atomically.
        """
        quo = await QuotationService.get_quotation(session, organization_id, quotation_id)

        if quo.status == QuotationStatus.CONVERTED:
            raise InvalidQuotationStateError(f"Quotation {quo.quotation_number} has already been converted.")
        if quo.status == QuotationStatus.CANCELLED:
            raise InvalidQuotationStateError("Cancelled quotation cannot be converted to subscription.")

        # Compute total items quantity to validate plan minimum quantity
        total_quantity = sum(line.quantity for line in quo.lines) or 1
        plan = quo.plan
        PlanService.validate_subscription_eligibility(plan, quantity=total_quantity, target_date=quo.start_date)

        # Calculate initial next billing date
        next_billing = advance_date(quo.start_date, plan.billing_interval, plan.interval_count)
        sub_number = await QuotationService._generate_subscription_number(session, organization_id)

        # Create Subscription
        subscription = Subscription(
            organization_id=organization_id,
            subscription_number=sub_number,
            customer_id=quo.customer_id,
            plan_id=quo.plan_id,
            quotation_id=quo.id,
            start_date=quo.start_date,
            expiry_date=quo.expiry_date,
            next_billing_date=next_billing,
            last_billed_date=None,
            payment_terms=quo.payment_terms,
            status=SubscriptionStatus.ACTIVE,
            # Policy toggles snapshot
            auto_close_on_expiry=plan.auto_close_on_expiry,
            allow_early_close=plan.allow_early_close,
            allow_pause=plan.allow_pause,
            allow_renewal=plan.allow_renewal,
            # Financial totals
            subtotal=quo.subtotal,
            tax_amount=quo.tax_amount,
            discount_amount=quo.discount_amount,
            total_amount=quo.total_amount,
            notes=quo.notes,
        )
        session.add(subscription)
        await session.flush()

        # Copy lines
        for q_line in quo.lines:
            is_addon = False
            if q_line.product and q_line.product.product_type == ProductType.ADDON:
                is_addon = True

            sub_line = SubscriptionLine(
                organization_id=organization_id,
                subscription_id=subscription.id,
                product_id=q_line.product_id,
                variant_id=q_line.variant_id,
                quantity=q_line.quantity,
                unit_price=q_line.unit_price,
                tax_id=q_line.tax_id,
                discount_rule_id=q_line.discount_rule_id,
                tax_amount=q_line.tax_amount,
                discount_amount=q_line.discount_amount,
                line_total=q_line.line_total,
                is_addon=is_addon,
            )
            session.add(sub_line)

        # Mark quote converted
        quo.status = QuotationStatus.CONVERTED

        await session.commit()

        # Return subscription with all relationships loaded
        stmt = (
            select(Subscription)
            .options(
                selectinload(Subscription.lines).selectinload(SubscriptionLine.product),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.variant),
                selectinload(Subscription.customer),
                selectinload(Subscription.plan),
            )
            .where(Subscription.id == subscription.id)
        )
        res = await session.execute(stmt)
        return res.scalars().first()
