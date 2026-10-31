"""Create invoices and invoice_lines tables

Revision ID: a7e4b912c03f
Revises: e82d3f5a9123
Create Date: 2026-10-31 12:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7e4b912c03f'
down_revision: Union[str, Sequence[str], None] = 'e82d3f5a9123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. invoices
    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('invoice_number', sa.String(length=100), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('invoice_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('payment_terms', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='draft'),
        sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('amount_paid', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('amount_due', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'invoice_number', name='uq_invoices_org_number'),
    )
    op.create_index(op.f('ix_invoices_id'), 'invoices', ['id'], unique=False)
    op.create_index(op.f('ix_invoices_organization_id'), 'invoices', ['organization_id'], unique=False)
    op.create_index(op.f('ix_invoices_invoice_number'), 'invoices', ['invoice_number'], unique=False)
    op.create_index(op.f('ix_invoices_subscription_id'), 'invoices', ['subscription_id'], unique=False)
    op.create_index(op.f('ix_invoices_customer_id'), 'invoices', ['customer_id'], unique=False)
    op.create_index(op.f('ix_invoices_due_date'), 'invoices', ['due_date'], unique=False)
    op.create_index(op.f('ix_invoices_status'), 'invoices', ['status'], unique=False)

    # 2. invoice_lines
    op.create_table(
        'invoice_lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('tax_id', sa.Integer(), nullable=True),
        sa.Column('discount_rule_id', sa.Integer(), nullable=True),
        sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('is_addon', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tax_id'], ['tax_rules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['discount_rule_id'], ['discount_rules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invoice_lines_id'), 'invoice_lines', ['id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_organization_id'), 'invoice_lines', ['organization_id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_invoice_id'), 'invoice_lines', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_product_id'), 'invoice_lines', ['product_id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_variant_id'), 'invoice_lines', ['variant_id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_tax_id'), 'invoice_lines', ['tax_id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_discount_rule_id'), 'invoice_lines', ['discount_rule_id'], unique=False)


def downgrade() -> None:
    op.drop_table('invoice_lines')
    op.drop_table('invoices')

