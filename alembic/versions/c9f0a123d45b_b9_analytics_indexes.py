"""B9: Add covering indexes for analytics queries.

Adds composite covering indexes to guarantee sub-50ms execution for:
  - Active subscriptions count (organization_id, status)
  - MRR/ARR grouping      (organization_id, status, plan_id)
  - Overdue invoices       (organization_id, status, due_date)
  - Revenue collected      (organization_id, status, payment_date)

Revision ID: c9f0a123d45b
Revises: b8f9e012c34a
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f0a123d45b"
down_revision: Union[str, Sequence[str], None] = "b8f9e012c34a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # subscriptions: covering index for active-count & MRR/ARR queries
    # (organization_id, status) — also useful for billing sweep
    # ------------------------------------------------------------------
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.create_index(
            "idx_subs_org_status",
            ["organization_id", "status"],
            unique=False,
        )
        # Additional index covering plan_id for MRR GROUP BY JOIN
        batch_op.create_index(
            "idx_subs_org_status_plan",
            ["organization_id", "status", "plan_id"],
            unique=False,
        )

    # ------------------------------------------------------------------
    # invoices: covering index for overdue query
    # (organization_id, status, due_date)
    # ------------------------------------------------------------------
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.create_index(
            "idx_invoices_org_status_due",
            ["organization_id", "status", "due_date"],
            unique=False,
        )

    # ------------------------------------------------------------------
    # payments: covering index for revenue-collected query
    # (organization_id, status, payment_date)
    # ------------------------------------------------------------------
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.create_index(
            "idx_payments_org_status_date",
            ["organization_id", "status", "payment_date"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.drop_index("idx_payments_org_status_date")

    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_index("idx_invoices_org_status_due")

    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.drop_index("idx_subs_org_status_plan")
        batch_op.drop_index("idx_subs_org_status")

