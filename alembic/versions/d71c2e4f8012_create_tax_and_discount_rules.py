"""Create tax_rules and discount_rules tables

Revision ID: d71c2e4f8012
Revises: f28a9b1c73de
Create Date: 2026-10-31 11:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd71c2e4f8012'
down_revision: Union[str, Sequence[str], None] = 'f28a9b1c73de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create tax_rules table
    op.create_table(
        'tax_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('rate', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tax_rules_id'), 'tax_rules', ['id'], unique=False)
    op.create_index(op.f('ix_tax_rules_organization_id'), 'tax_rules', ['organization_id'], unique=False)
    op.create_index(op.f('ix_tax_rules_name'), 'tax_rules', ['name'], unique=False)

    # 2. Create discount_rules table
    op.create_table(
        'discount_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('discount_type', sa.Enum('FIXED_AMOUNT', 'PERCENTAGE', name='discount_type_enum', native_enum=False), nullable=False),
        sa.Column('discount_value', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('min_purchase_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('min_quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('times_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('scope', sa.Enum('PRODUCT', 'SUBSCRIPTION', name='discount_scope_enum', native_enum=False), nullable=False, server_default='SUBSCRIPTION'),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_discount_rules_id'), 'discount_rules', ['id'], unique=False)
    op.create_index(op.f('ix_discount_rules_organization_id'), 'discount_rules', ['organization_id'], unique=False)
    op.create_index(op.f('ix_discount_rules_name'), 'discount_rules', ['name'], unique=False)
    op.create_index(op.f('ix_discount_rules_product_id'), 'discount_rules', ['product_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_discount_rules_product_id'), table_name='discount_rules')
    op.drop_index(op.f('ix_discount_rules_name'), table_name='discount_rules')
    op.drop_index(op.f('ix_discount_rules_organization_id'), table_name='discount_rules')
    op.drop_index(op.f('ix_discount_rules_id'), table_name='discount_rules')
    op.drop_table('discount_rules')

    op.drop_index(op.f('ix_tax_rules_name'), table_name='tax_rules')
    op.drop_index(op.f('ix_tax_rules_organization_id'), table_name='tax_rules')
    op.drop_index(op.f('ix_tax_rules_id'), table_name='tax_rules')
    op.drop_table('tax_rules')
