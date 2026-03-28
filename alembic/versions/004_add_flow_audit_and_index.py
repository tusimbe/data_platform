from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flow_step_audits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("flow_instance_id", sa.Integer(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("step_data", postgresql.JSON(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(["flow_instance_id"], ["flow_instances.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "flow_instances",
        sa.Column("source_record_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_flow_instances_source_record_id",
        "flow_instances",
        ["source_record_id"],
    )
    op.create_index(
        "ix_flow_instances_status_definition",
        "flow_instances",
        ["status", "flow_definition_id"],
    )
    op.create_index("ix_flow_step_audits_instance_id", "flow_step_audits", ["flow_instance_id"])


def downgrade() -> None:
    op.drop_index("ix_flow_step_audits_instance_id", table_name="flow_step_audits")
    op.drop_index("ix_flow_instances_status_definition", table_name="flow_instances")
    op.drop_index("ix_flow_instances_source_record_id", table_name="flow_instances")
    op.drop_column("flow_instances", "source_record_id")
    op.drop_table("flow_step_audits")
