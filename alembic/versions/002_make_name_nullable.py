"""make name and order_number columns nullable for partial data tolerance

Revision ID: 002
Revises: 001
Create Date: 2026-03-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("unified_customers", "name", existing_type=sa.String(200), nullable=True)
    op.alter_column("unified_products", "name", existing_type=sa.String(200), nullable=True)
    op.alter_column("unified_projects", "name", existing_type=sa.String(200), nullable=True)
    op.alter_column("unified_contacts", "name", existing_type=sa.String(200), nullable=True)
    op.alter_column("unified_orders", "order_number", existing_type=sa.String(100), nullable=True)


def downgrade() -> None:
    op.alter_column("unified_orders", "order_number", existing_type=sa.String(100), nullable=False)
    op.alter_column("unified_contacts", "name", existing_type=sa.String(200), nullable=False)
    op.alter_column("unified_projects", "name", existing_type=sa.String(200), nullable=False)
    op.alter_column("unified_products", "name", existing_type=sa.String(200), nullable=False)
    op.alter_column("unified_customers", "name", existing_type=sa.String(200), nullable=False)
