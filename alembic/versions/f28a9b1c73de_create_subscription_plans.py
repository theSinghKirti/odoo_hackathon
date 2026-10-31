"""Create subscription_plans table

Revision ID: f28a9b1c73de
Revises: c4d1b82a101f
Create Date: 2026-10-31 11:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f28a9b1c73de'
down_revision: Union[str, Sequence[str], None] = 'c4d1b82a101f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subscription_plans',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('billing_interval', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY', name='billing_interval_enum', native_enum=False), nullable=False),
        sa.Column('interval_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('base_price', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column('min_quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('available_from', sa.Date(), nullable=True),
        sa.Column('available_until', sa.Date(), nullable=True),
        sa.Column('auto_close_on_expiry', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_early_close', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_pause', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_renewal', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subscription_plans_id'), 'subscription_plans', ['id'], unique=False)
    op.create_index(op.f('ix_subscription_plans_organization_id'), 'subscription_plans', ['organization_id'], unique=False)
    op.create_index(op.f('ix_subscription_plans_name'), 'subscription_plans', ['name'], unique=False)
    op.create_index(op.f('ix_subscription_plans_billing_interval'), 'subscription_plans', ['billing_interval'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_subscription_plans_billing_interval'), table_name='subscription_plans')
    op.drop_index(op.f('ix_subscription_plans_name'), table_name='subscription_plans')
    op.drop_index(op.f('ix_subscription_plans_organization_id'), table_name='subscription_plans')
    op.drop_index(op.f('ix_subscription_plans_id'), table_name='subscription_plans')
    op.drop_table('subscription_plans')
