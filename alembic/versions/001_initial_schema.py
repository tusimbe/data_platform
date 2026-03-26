"""initial schema - all tables for data platform

Revision ID: 001
Revises:
Create Date: 2026-03-26

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables for the data platform."""

    # --- connectors ---
    op.create_table(
        "connectors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("connector_type", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("auth_config", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # --- sync_tasks ---
    op.create_table(
        "sync_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("cron_expression", sa.String(length=100), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("config", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- sync_logs ---
    op.create_table(
        "sync_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sync_task_id", sa.Integer(), nullable=True),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_records", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("success_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("failure_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("error_details", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["sync_task_id"], ["sync_tasks.id"]),
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- raw_data ---
    op.create_table(
        "raw_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("data", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sync_log_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"]),
        sa.ForeignKeyConstraint(["sync_log_id"], ["sync_logs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "entity", "external_id", name="uq_raw_data_source"),
    )

    # --- field_mappings ---
    op.create_table(
        "field_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_type", sa.String(length=50), nullable=False),
        sa.Column("source_entity", sa.String(length=100), nullable=False),
        sa.Column("target_table", sa.String(length=100), nullable=False),
        sa.Column("source_field", sa.String(length=100), nullable=False),
        sa.Column("target_field", sa.String(length=100), nullable=False),
        sa.Column("transform", sa.String(length=50), nullable=True),
        sa.Column("transform_config", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- entity_schemas ---
    op.create_table(
        "entity_schemas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_type", sa.String(length=50), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=False),
        sa.Column("schema_data", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- unified_customers ---
    op.create_table(
        "unified_customers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_data_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "external_id", name="uq_customers_source_external"),
    )

    # --- unified_orders ---
    op.create_table(
        "unified_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_data_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("order_number", sa.String(length=100), nullable=False),
        sa.Column("order_type", sa.String(length=20), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "external_id", name="uq_orders_source_external"),
    )

    # --- unified_products ---
    op.create_table(
        "unified_products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_data_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "external_id", name="uq_products_source_external"),
    )

    # --- unified_inventory ---
    op.create_table(
        "unified_inventory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_data_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("warehouse", sa.String(length=100), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("available_quantity", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "external_id", name="uq_inventory_source_external"),
    )

    # --- unified_projects ---
    op.create_table(
        "unified_projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_data_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("owner", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "external_id", name="uq_projects_source_external"),
    )

    # --- unified_contacts ---
    op.create_table(
        "unified_contacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_data_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "external_id", name="uq_contacts_source_external"),
    )

    # --- Indexes for common query patterns ---
    op.create_index("ix_raw_data_connector_entity", "raw_data", ["connector_id", "entity"])
    op.create_index("ix_sync_logs_connector_id", "sync_logs", ["connector_id"])
    op.create_index("ix_sync_logs_sync_task_id", "sync_logs", ["sync_task_id"])
    op.create_index("ix_sync_tasks_connector_id", "sync_tasks", ["connector_id"])


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_index("ix_sync_tasks_connector_id", table_name="sync_tasks")
    op.drop_index("ix_sync_logs_sync_task_id", table_name="sync_logs")
    op.drop_index("ix_sync_logs_connector_id", table_name="sync_logs")
    op.drop_index("ix_raw_data_connector_entity", table_name="raw_data")

    op.drop_table("unified_contacts")
    op.drop_table("unified_projects")
    op.drop_table("unified_inventory")
    op.drop_table("unified_products")
    op.drop_table("unified_orders")
    op.drop_table("unified_customers")
    op.drop_table("entity_schemas")
    op.drop_table("field_mappings")
    op.drop_table("raw_data")
    op.drop_table("sync_logs")
    op.drop_table("sync_tasks")
    op.drop_table("connectors")
