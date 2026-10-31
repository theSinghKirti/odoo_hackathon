from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.discount import DiscountRule, DiscountScope
from app.models.invoice import Invoice, InvoiceLine, InvoiceStatus
from app.models.plan import BillingInterval
from app.models.product import Product, ProductVariant
from app.models.subscription import Subscription, SubscriptionLine, SubscriptionStatus
from app.models.tax import TaxRule
from app.models.user import User, UserRole
from app.schemas.invoice import InvoiceCreate
from app.services.discount_service import DiscountService
from app.services.quotation_service import advance_date
from app.services.tax_service import TaxService


class InvoiceServiceError(Exception):
    """Base exception for invoicing and billing errors."""
    pass


class InvoiceNotFoundError(InvoiceServiceError):
    pass


class InvalidInvoiceStateError(InvoiceServiceError):
    pass


class InvoiceAccessDeniedError(InvoiceServiceError):
    pass


class InvoiceService:
    @staticmethod
    async def _generate_invoice_number(session: AsyncSession, organization_id: int) -> str:
        """
        Generates sequential invoice identifier: INV-YYYY-XXXX scoped by tenant organization.
        """
        year = date.today().year
        stmt = select(func.count(Invoice.id)).where(Invoice.organization_id == organization_id)
        res = await session.execute(stmt)
        count = res.scalar() or 0
        return f"INV-{year}-{count + 1:04d}"

    @staticmethod
    async def get_invoice(
        session: AsyncSession,
        organization_id: int,
        invoice_id: int,
        user: Optional[User] = None,
    ) -> Invoice:
        """
        Retrieves an invoice with its lines, customer, and subscription relationships.
        Enforces tenant isolation and customer portal ownership.
        """
        stmt = (
            select(Invoice)
            .options(
                selectinload(Invoice.lines).selectinload(InvoiceLine.product),
                selectinload(Invoice.lines).selectinload(InvoiceLine.variant),
                selectinload(Invoice.lines).selectinload(InvoiceLine.tax_rule),
                selectinload(Invoice.lines).selectinload(InvoiceLine.discount_rule),
                selectinload(Invoice.customer),
                selectinload(Invoice.subscription),
                selectinload(Invoice.payments),
            )
            .where(
                and_(
                    Invoice.id == invoice_id,
                    Invoice.organization_id == organization_id,
                )
            )
        )
        res = await session.execute(stmt)
        inv = res.scalars().first()
        if not inv:
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found in this organization.")

        # Customer portal access restriction
        if user and user.role == UserRole.CUSTOMER:
            if inv.customer.user_id != user.id and inv.customer.email.lower() != user.email.lower():
                raise InvoiceAccessDeniedError("Access to this invoice is restricted to its owner.")

        return inv

    @staticmethod
    async def list_invoices(
        session: AsyncSession,
        organization_id: int,
        status: Optional[InvoiceStatus] = None,
        customer_id: Optional[int] = None,
        subscription_id: Optional[int] = None,
        user: Optional[User] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Invoice]:
        """
        Lists invoices scoped strictly to tenant organization.
        Customer role is automatically restricted to owned invoices.
        """
        filters = [Invoice.organization_id == organization_id]

        if user and user.role == UserRole.CUSTOMER:
            c_stmt = select(Customer.id).where(
                and_(
                    Customer.organization_id == organization_id,
                    (Customer.user_id == user.id) | (Customer.email == user.email),
                )
            )
            c_res = await session.execute(c_stmt)
            owned_ids = c_res.scalars().all()
            if not owned_ids:
                return []
            filters.append(Invoice.customer_id.in_(owned_ids))
        elif customer_id:
            filters.append(Invoice.customer_id == customer_id)

        if status:
            filters.append(Invoice.status == status)

        if subscription_id:
            filters.append(Invoice.subscription_id == subscription_id)

        stmt = (
            select(Invoice)
            .options(
                selectinload(Invoice.lines).selectinload(InvoiceLine.product),
                selectinload(Invoice.lines).selectinload(InvoiceLine.variant),
                selectinload(Invoice.customer),
            )
            .where(and_(*filters))
            .order_by(Invoice.id.desc())
            .offset(skip)
            .limit(limit)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def confirm_invoice(
        session: AsyncSession,
        organization_id: int,
        invoice_id: int,
        user: Optional[User] = None,
    ) -> Invoice:
        """
        Staff/Admin action to confirm a Draft invoice:
        Draft -> Confirmed.
        Locks invoice lines from editing.
        """
        if user and user.role == UserRole.CUSTOMER:
            raise InvoiceAccessDeniedError("Customers cannot confirm invoices.")

        inv = await InvoiceService.get_invoice(session, organization_id, invoice_id, user=user)

        if inv.status != InvoiceStatus.DRAFT:
            raise InvalidInvoiceStateError(
                f"Cannot confirm invoice {inv.invoice_number}. Only 'Draft' invoices can be confirmed (current status: '{inv.status.value}')."
            )

        inv.status = InvoiceStatus.CONFIRMED
        await session.commit()
        await session.refresh(inv)
        return inv

    @staticmethod
    async def cancel_invoice(
        session: AsyncSession,
        organization_id: int,
        invoice_id: int,
        reason: Optional[str] = None,
        user: Optional[User] = None,
    ) -> Invoice:
        """
        Staff/Admin action to cancel/void an unpaid invoice:
        Draft / Confirmed -> Cancelled.
        Paid invoices are immutable and cannot be cancelled.
        """
        if user and user.role == UserRole.CUSTOMER:
            raise InvoiceAccessDeniedError("Customers cannot cancel invoices.")

        inv = await InvoiceService.get_invoice(session, organization_id, invoice_id, user=user)

        if inv.status == InvoiceStatus.PAID:
            raise InvalidInvoiceStateError(
                f"Paid invoices are immutable financial documents and cannot be cancelled. Corrections must occur via credit adjustments."
            )

        if inv.status == InvoiceStatus.CANCELLED:
            raise InvalidInvoiceStateError(f"Invoice {inv.invoice_number} is already cancelled.")

        inv.status = InvoiceStatus.CANCELLED
        inv.amount_due = Decimal("0.00")
        if reason:
            existing = f"{inv.notes}\n" if inv.notes else ""
            inv.notes = f"{existing}Cancellation reason: {reason.strip()}"

        await session.commit()
        await session.refresh(inv)
        return inv

    @staticmethod
    async def create_invoice_for_subscription(
        session: AsyncSession,
        organization_id: int,
        subscription_id: int,
        invoice_date: Optional[date] = None,
        due_date: Optional[date] = None,
    ) -> Invoice:
        """
        Generates an invoice from an active subscription.
        Computes line-level taxes, discounts, and advances.
        """
        stmt = (
            select(Subscription)
            .options(
                selectinload(Subscription.lines).selectinload(SubscriptionLine.product),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.variant),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.tax_rule),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.discount_rule),
                selectinload(Subscription.customer),
                selectinload(Subscription.plan),
            )
            .where(
                and_(
                    Subscription.id == subscription_id,
                    Subscription.organization_id == organization_id,
                )
            )
        )
        res = await session.execute(stmt)
        sub = res.scalars().first()
        if not sub:
            raise InvoiceNotFoundError(f"Subscription {subscription_id} not found.")

        if sub.status != SubscriptionStatus.ACTIVE:
            raise InvalidInvoiceStateError(
                f"Cannot generate invoice for subscription {sub.subscription_number} in '{sub.status.value}' state. Must be Active."
            )

        inv_date = invoice_date or date.today()
        inv_due = due_date or (inv_date + timedelta(days=15))

        inv_number = await InvoiceService._generate_invoice_number(session, organization_id)

        invoice = Invoice(
            organization_id=organization_id,
            invoice_number=inv_number,
            subscription_id=sub.id,
            customer_id=sub.customer_id,
            invoice_date=inv_date,
            due_date=inv_due,
            payment_terms=sub.payment_terms or "Due on Receipt",
            status=InvoiceStatus.DRAFT,
            subtotal=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
            amount_due=Decimal("0.00"),
            notes=f"Generated for Subscription {sub.subscription_number}",
        )
        session.add(invoice)
        await session.flush()

        subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_discount = Decimal("0.00")

        for line in sub.lines:
            base_line = round(line.unit_price * line.quantity, 2)
            subtotal += base_line

            # Evaluate discount if discount rule attached
            discount_val = Decimal("0.00")
            if line.discount_rule_id:
                is_app, discount_val = await DiscountService.evaluate_and_apply_discount(
                    session=session,
                    organization_id=organization_id,
                    rule_id=line.discount_rule_id,
                    base_amount=base_line,
                    quantity=line.quantity,
                    target_date=inv_date,
                    target_product_id=line.product_id,
                    record_usage=True,
                )
            total_discount += discount_val

            # Tax evaluation on (amount - discount)
            taxable = max(Decimal("0.00"), base_line - discount_val)
            tax_val = Decimal("0.00")
            if line.tax_id and line.tax_rule and line.tax_rule.is_active:
                tax_val = TaxService.compute_tax(taxable, line.tax_rule.rate)
            total_tax += tax_val

            line_total = taxable + tax_val

            inv_line = InvoiceLine(
                organization_id=organization_id,
                invoice_id=invoice.id,
                product_id=line.product_id,
                variant_id=line.variant_id,
                description=f"{line.product.name} ({line.variant.attribute_value})" if line.variant else line.product.name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_id=line.tax_id,
                discount_rule_id=line.discount_rule_id,
                tax_amount=tax_val,
                discount_amount=discount_val,
                line_total=line_total,
                is_addon=line.is_addon,
            )
            session.add(inv_line)

        final_total = max(Decimal("0.00"), subtotal - total_discount + total_tax)
        invoice.subtotal = subtotal
        invoice.tax_amount = total_tax
        invoice.discount_amount = total_discount
        invoice.total_amount = final_total
        invoice.amount_paid = Decimal("0.00")
        invoice.amount_due = final_total

        await session.commit()
        return await InvoiceService.get_invoice(session, organization_id, invoice.id)

    @staticmethod
    async def run_billing_sweep(
        session: AsyncSession,
        as_of_date: Optional[date] = None,
        organization_id: Optional[int] = None,
    ) -> List[Invoice]:
        """
        Automated Idempotent Billing Sweep:
        1. Selects active subscriptions where next_billing_date <= as_of_date.
        2. Applies concurrency lock (SELECT ... FOR UPDATE SKIP LOCKED on PostgreSQL).
        3. Enforces idempotency guard: last_billed_date < next_billing_date.
        4. Generates Draft invoice with tax/discount rules.
        5. Advances next_billing_date according to plan interval (daily/weekly/monthly/yearly).
        6. Updates last_billed_date = as_of_date.
        7. Enforces plan auto_close_on_expiry if contract expires.
        """
        today = as_of_date or date.today()

        filters = [
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.next_billing_date <= today,
        ]
        if organization_id:
            filters.append(Subscription.organization_id == organization_id)

        stmt = (
            select(Subscription)
            .options(
                selectinload(Subscription.lines).selectinload(SubscriptionLine.product),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.variant),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.tax_rule),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.discount_rule),
                selectinload(Subscription.customer),
                selectinload(Subscription.plan),
            )
            .where(and_(*filters))
            .order_by(Subscription.id.asc())
        )

        # Apply row-level lock on PostgreSQL; SQLite silently proceeds without it
        dialect_name = session.bind.dialect.name if session.bind else ""
        if dialect_name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        res = await session.execute(stmt)
        due_subscriptions = list(res.scalars().all())

        generated_invoices: List[Invoice] = []

        for sub in due_subscriptions:
            # Idempotency guard: Prevent duplicate billing in the same cycle
            if sub.last_billed_date is not None and sub.last_billed_date >= sub.next_billing_date:
                continue

            inv_number = await InvoiceService._generate_invoice_number(session, sub.organization_id)
            inv_date = sub.next_billing_date
            inv_due = inv_date + timedelta(days=15)

            invoice = Invoice(
                organization_id=sub.organization_id,
                invoice_number=inv_number,
                subscription_id=sub.id,
                customer_id=sub.customer_id,
                invoice_date=inv_date,
                due_date=inv_due,
                payment_terms=sub.payment_terms or "Due on Receipt",
                status=InvoiceStatus.DRAFT,
                subtotal=Decimal("0.00"),
                tax_amount=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                total_amount=Decimal("0.00"),
                amount_paid=Decimal("0.00"),
                amount_due=Decimal("0.00"),
                notes=f"Automated Billing Sweep invoice for Subscription {sub.subscription_number}",
            )
            session.add(invoice)
            await session.flush()

            subtotal = Decimal("0.00")
            total_tax = Decimal("0.00")
            total_discount = Decimal("0.00")

            for line in sub.lines:
                base_line = round(line.unit_price * line.quantity, 2)
                subtotal += base_line

                # Discount rule application
                discount_val = Decimal("0.00")
                if line.discount_rule_id:
                    is_app, discount_val = await DiscountService.evaluate_and_apply_discount(
                        session=session,
                        organization_id=sub.organization_id,
                        rule_id=line.discount_rule_id,
                        base_amount=base_line,
                        quantity=line.quantity,
                        target_date=inv_date,
                        target_product_id=line.product_id,
                        record_usage=True,
                    )
                total_discount += discount_val

                # Tax rule computation
                taxable = max(Decimal("0.00"), base_line - discount_val)
                tax_val = Decimal("0.00")
                if line.tax_id and line.tax_rule and line.tax_rule.is_active:
                    tax_val = TaxService.compute_tax(taxable, line.tax_rule.rate)
                total_tax += tax_val

                line_total = taxable + tax_val

                inv_line = InvoiceLine(
                    organization_id=sub.organization_id,
                    invoice_id=invoice.id,
                    product_id=line.product_id,
                    variant_id=line.variant_id,
                    description=f"{line.product.name} ({line.variant.attribute_value})" if line.variant else line.product.name,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    tax_id=line.tax_id,
                    discount_rule_id=line.discount_rule_id,
                    tax_amount=tax_val,
                    discount_amount=discount_val,
                    line_total=line_total,
                    is_addon=line.is_addon,
                )
                session.add(inv_line)

            final_total = max(Decimal("0.00"), subtotal - total_discount + total_tax)
            invoice.subtotal = subtotal
            invoice.tax_amount = total_tax
            invoice.discount_amount = total_discount
            invoice.total_amount = final_total
            invoice.amount_paid = Decimal("0.00")
            invoice.amount_due = final_total

            # Advance subscription cycle
            sub.last_billed_date = today
            plan = sub.plan
            new_next_billing = advance_date(sub.next_billing_date, plan.billing_interval, plan.interval_count)
            sub.next_billing_date = new_next_billing

            # Lifecycle check: Auto-close on expiry if policy configured and subscription has elapsed
            if sub.auto_close_on_expiry and sub.next_billing_date > sub.expiry_date:
                sub.status = SubscriptionStatus.CLOSED

            generated_invoices.append(invoice)

        await session.commit()
        return generated_invoices

