"""
B9 — AnalyticsService: ORM-based aggregation engine for MRR/ARR, revenue, and overdue reporting.

Business Rules (§12):
  MRR = Σ(daily × 30) + Σ(weekly × 4.33) + Σ(monthly × 1) + Σ(yearly ÷ 12)
  ARR = MRR × 12

All monetary arithmetic uses Python Decimal to preserve NUMERIC(12,2) integrity.
Uses SQLAlchemy ORM select() expressions for proper session transaction participation.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentStatus
from app.models.plan import BillingInterval, SubscriptionPlan
from app.models.subscription import Subscription, SubscriptionStatus
from app.schemas.analytics import AnalyticsSummary, MRRBreakdown, OverdueInvoiceSummary

# MRR normalization multipliers per billing interval (Decimal for precision)
_INTERVAL_MULTIPLIER: dict[str, Decimal] = {
    BillingInterval.DAILY.value: Decimal("30"),
    BillingInterval.WEEKLY.value: Decimal("4.33"),
    BillingInterval.MONTHLY.value: Decimal("1"),
    BillingInterval.YEARLY.value: Decimal("1") / Decimal("12"),
}

_TWO_PLACES = Decimal("0.01")


class AnalyticsService:
    """
    Provides aggregated KPI metrics for a single tenant (organization).

    All queries are scoped to organization_id to enforce multi-tenant isolation.
    Uses SQLAlchemy ORM select() expressions to participate correctly in the
    session's transaction lifecycle (compatible with both SQLite test DB and
    PostgreSQL production DB).
    """

    # ------------------------------------------------------------------
    # Public: composite summary
    # ------------------------------------------------------------------

    @staticmethod
    async def get_summary(
        session: AsyncSession,
        organization_id: int,
        revenue_start: Optional[date] = None,
        revenue_end: Optional[date] = None,
    ) -> AnalyticsSummary:
        """
        Return all KPI metrics in a single call.

        Args:
            session: Async SQLAlchemy session.
            organization_id: Tenant scope — never omit.
            revenue_start: Inclusive start date for collected-revenue window.
            revenue_end: Inclusive end date for collected-revenue window.

        Returns:
            AnalyticsSummary containing subscriptions, MRR/ARR, revenue, overdue.
        """
        active_count = await AnalyticsService.get_active_subscriptions_count(
            session, organization_id
        )
        mrr_arr = await AnalyticsService.get_mrr_arr(session, organization_id)
        revenue = await AnalyticsService.get_revenue_collected(
            session, organization_id, revenue_start, revenue_end
        )
        overdue = await AnalyticsService.get_overdue_invoices(session, organization_id)

        return AnalyticsSummary(
            organization_id=organization_id,
            as_of_date=date.today(),
            active_subscriptions_count=active_count,
            mrr_arr=mrr_arr,
            revenue_start_date=revenue_start,
            revenue_end_date=revenue_end,
            revenue_collected=revenue,
            overdue_invoices=overdue,
        )

    # ------------------------------------------------------------------
    # Active subscriptions count
    # ------------------------------------------------------------------

    @staticmethod
    async def get_active_subscriptions_count(
        session: AsyncSession,
        organization_id: int,
    ) -> int:
        """
        Count subscriptions with status = ACTIVE for the given organization.

        Uses the covering index idx_subs_org_status (organization_id, status).
        """
        stmt = select(func.count(Subscription.id)).where(
            and_(
                Subscription.organization_id == organization_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    # ------------------------------------------------------------------
    # MRR / ARR
    # ------------------------------------------------------------------

    @staticmethod
    async def get_mrr_arr(
        session: AsyncSession,
        organization_id: int,
    ) -> MRRBreakdown:
        """
        Compute MRR and ARR by normalizing each active subscription's
        total_amount to a monthly equivalent via a JOIN to subscription_plans.

        Formula (Business Rules §12):
          MRR = Σ(daily × 30) + Σ(weekly × 4.33) + Σ(monthly × 1) + Σ(yearly ÷ 12)
          ARR = MRR × 12

        Returns per-interval contributions and aggregate MRR/ARR.
        """
        stmt = (
            select(SubscriptionPlan.billing_interval, func.sum(Subscription.total_amount))
            .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
            .where(
                and_(
                    Subscription.organization_id == organization_id,
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            )
            .group_by(SubscriptionPlan.billing_interval)
        )
        result = await session.execute(stmt)
        rows = result.fetchall()

        # Aggregate per interval using Decimal arithmetic
        interval_totals: dict[str, Decimal] = {k: Decimal("0.00") for k in _INTERVAL_MULTIPLIER}
        for row in rows:
            interval_value = (row[0].value if hasattr(row[0], "value") else str(row[0])).lower()
            total = Decimal(str(row[1] or "0"))
            if interval_value in interval_totals:
                interval_totals[interval_value] += total

        daily_contrib = (
            interval_totals[BillingInterval.DAILY.value] * _INTERVAL_MULTIPLIER[BillingInterval.DAILY.value]
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        weekly_contrib = (
            interval_totals[BillingInterval.WEEKLY.value] * _INTERVAL_MULTIPLIER[BillingInterval.WEEKLY.value]
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        monthly_contrib = (
            interval_totals[BillingInterval.MONTHLY.value] * _INTERVAL_MULTIPLIER[BillingInterval.MONTHLY.value]
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        yearly_contrib = (
            interval_totals[BillingInterval.YEARLY.value] * _INTERVAL_MULTIPLIER[BillingInterval.YEARLY.value]
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        mrr = (daily_contrib + weekly_contrib + monthly_contrib + yearly_contrib).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )
        arr = (mrr * Decimal("12")).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

        return MRRBreakdown(
            daily_contribution=daily_contrib,
            weekly_contribution=weekly_contrib,
            monthly_contribution=monthly_contrib,
            yearly_contribution=yearly_contrib,
            mrr=mrr,
            arr=arr,
        )

    # ------------------------------------------------------------------
    # Revenue collected
    # ------------------------------------------------------------------

    @staticmethod
    async def get_revenue_collected(
        session: AsyncSession,
        organization_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Decimal:
        """
        Sum all succeeded payments within an optional date window.

        Args:
            session: Async DB session.
            organization_id: Tenant scope.
            start_date: Inclusive start of payment_date window (optional).
            end_date: Inclusive end of payment_date window (optional).

        Returns:
            Decimal total of payments.amount WHERE status=SUCCEEDED.
        """
        conditions = [
            Payment.organization_id == organization_id,
            Payment.status == PaymentStatus.SUCCEEDED,
        ]
        if start_date:
            conditions.append(Payment.payment_date >= start_date)
        if end_date:
            conditions.append(Payment.payment_date <= end_date)

        stmt = select(func.sum(Payment.amount)).where(and_(*conditions))
        result = await session.execute(stmt)
        total = result.scalar()
        if total is None:
            return Decimal("0.00")
        return Decimal(str(total)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # Overdue invoices
    # ------------------------------------------------------------------

    @staticmethod
    async def get_overdue_invoices(
        session: AsyncSession,
        organization_id: int,
    ) -> OverdueInvoiceSummary:
        """
        Count and total the amount_due of confirmed invoices past their due_date.

        An invoice is overdue when:
          status = CONFIRMED   (not yet paid or cancelled)
          due_date < today

        Uses the covering index idx_invoices_org_status_due.
        """
        today = date.today()
        conditions = [
            Invoice.organization_id == organization_id,
            Invoice.status == InvoiceStatus.CONFIRMED,
            Invoice.due_date < today,
        ]

        count_stmt = select(func.count(Invoice.id)).where(and_(*conditions))
        sum_stmt = select(func.sum(Invoice.amount_due)).where(and_(*conditions))

        count_result = await session.execute(count_stmt)
        sum_result = await session.execute(sum_stmt)

        count = count_result.scalar() or 0
        total_raw = sum_result.scalar()
        total_due = (
            Decimal(str(total_raw)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
            if total_raw is not None
            else Decimal("0.00")
        )
        return OverdueInvoiceSummary(count=count, total_amount_due=total_due)
