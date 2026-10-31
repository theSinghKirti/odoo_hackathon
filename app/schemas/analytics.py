"""
Pydantic response schemas for B9 Reporting & Analytical Aggregations.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class MRRBreakdown(BaseModel):
    """MRR contribution breakdown by billing interval."""

    daily_contribution: Decimal = Field(
        ..., description="Sum of daily-billed subscription totals × 30"
    )
    weekly_contribution: Decimal = Field(
        ..., description="Sum of weekly-billed subscription totals × 4.33"
    )
    monthly_contribution: Decimal = Field(
        ..., description="Sum of monthly-billed subscription totals (face value)"
    )
    yearly_contribution: Decimal = Field(
        ..., description="Sum of yearly-billed subscription totals ÷ 12"
    )
    mrr: Decimal = Field(..., description="Total Monthly Recurring Revenue")
    arr: Decimal = Field(..., description="Annual Recurring Revenue = MRR × 12")


class OverdueInvoiceSummary(BaseModel):
    """Count and total value of overdue confirmed invoices."""

    count: int = Field(..., description="Number of overdue invoices")
    total_amount_due: Decimal = Field(
        ..., description="Sum of amount_due on all overdue invoices"
    )


class AnalyticsSummary(BaseModel):
    """
    Full analytics snapshot for an organization.

    All monetary values use NUMERIC(12,2) precision (Decimal).
    """

    organization_id: int
    as_of_date: date = Field(..., description="Date the snapshot was computed")

    # Subscriptions
    active_subscriptions_count: int = Field(
        ..., description="Number of subscriptions with status='active'"
    )

    # Revenue
    mrr_arr: MRRBreakdown

    # Payments collected in a specific window (optional filters)
    revenue_start_date: Optional[date] = Field(
        None, description="Start of revenue collection window"
    )
    revenue_end_date: Optional[date] = Field(
        None, description="End of revenue collection window"
    )
    revenue_collected: Decimal = Field(
        ...,
        description="Sum of succeeded payment amounts within the requested window",
    )

    # Overdue
    overdue_invoices: OverdueInvoiceSummary

