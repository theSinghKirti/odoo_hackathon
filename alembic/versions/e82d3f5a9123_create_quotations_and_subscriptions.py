"""Create quotation and subscription tables

Revision ID: e82d3f5a9123
Revises: d71c2e4f8012
Create Date: 2026-10-31 12:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e82d3f5a9123'
down_revision: Union[str, Sequence[str], None] = 'd71c2e4f8012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. quotation_templates
    op.create_table(
        'quotation_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('validity_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quotation_templates_id'), 'quotation_templates', ['id'], unique=False)
    op.create_index(op.f('ix_quotation_templates_organization_id'), 'quotation_templates', ['organization_id'], unique=False)
    op.create_index(op.f('ix_quotation_templates_name'), 'quotation_templates', ['name'], unique=False)

    # 2. quotation_template_lines
    op.create_table(
        'quotation_template_lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['quotation_templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quotation_template_lines_id'), 'quotation_template_lines', ['id'], unique=False)

    # 3. quotations
    op.create_table(
        'quotations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('quotation_number', sa.String(length=100), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('payment_terms', sa.String(length=255), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'QUOTATION', 'CONFIRMED', 'CONVERTED', 'CANCELLED', name='quotation_status_enum', native_enum=False), nullable=False, server_default='DRAFT'),
        sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['template_id'], ['quotation_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'quotation_number', name='uq_quotations_org_number'),
    )
    op.create_index(op.f('ix_quotations_id'), 'quotations', ['id'], unique=False)
    op.create_index(op.f('ix_quotations_quotation_number'), 'quotations', ['quotation_number'], unique=False)
    op.create_index(op.f('ix_quotations_organization_id'), 'quotations', ['organization_id'], unique=False)
    op.create_index(op.f('ix_quotations_customer_id'), 'quotations', ['customer_id'], unique=False)
    op.create_index(op.f('ix_quotations_plan_id'), 'quotations', ['plan_id'], unique=False)

    # 4. quotation_lines
    op.create_table(
        'quotation_lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('quotation_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('tax_id', sa.Integer(), nullable=True),
        sa.Column('discount_rule_id', sa.Integer(), nullable=True),
        sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['quotation_id'], ['quotations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tax_id'], ['tax_rules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['discount_rule_id'], ['discount_rules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quotation_lines_id'), 'quotation_lines', ['id'], unique=False)

    # 5. subscriptions
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('subscription_number', sa.String(length=100), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('quotation_id', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('next_billing_date', sa.Date(), nullable=False),
        sa.Column('last_billed_date', sa.Date(), nullable=True),
        sa.Column('payment_terms', sa.String(length=255), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'QUOTATION', 'CONFIRMED', 'ACTIVE', 'PAUSED', 'CLOSED', name='subscription_status_enum', native_enum=False), nullable=False, server_default='ACTIVE'),
        sa.Column('auto_close_on_expiry', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_early_close', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_pause', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_renewal', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['quotation_id'], ['quotations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'subscription_number', name='uq_subscriptions_org_number'),
    )
    op.create_index(op.f('ix_subscriptions_id'), 'subscriptions', ['id'], unique=False)
    op.create_index(op.f('ix_subscriptions_subscription_number'), 'subscriptions', ['subscription_number'], unique=False)
    op.create_index(op.f('ix_subscriptions_organization_id'), 'subscriptions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_next_billing_date'), 'subscriptions', ['next_billing_date'], unique=False)

    # 6. subscription_lines
    op.create_table(
        'subscription_lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('tax_id', sa.Integer(), nullable=True),
        sa.Column('discount_rule_id', sa.Integer(), nullable=True),
        sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('is_addon', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tax_id'], ['tax_rules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['discount_rule_id'], ['discount_rules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subscription_lines_id'), 'subscription_lines', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('subscription_lines')
    op.drop_table('subscriptions')
    op.drop_table('quotation_lines')
    op.drop_table('quotations')
    op.drop_table('quotation_template_lines')
    op.drop_table('quotation_templates')
