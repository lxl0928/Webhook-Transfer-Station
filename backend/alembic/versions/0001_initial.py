"""Initial durable webhook queue and configuration schema."""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tb_user",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("real_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("llm_host", sa.String(512), nullable=False),
        sa.Column("llm_api_key", sa.Text(), nullable=False),
        sa.Column("llm_model", sa.String(128), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "tb_webhooks",
        sa.Column("wid", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("tb_user.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_url", sa.String(512), nullable=False),
        sa.Column("source_info", sa.JSON(), nullable=False),
        sa.Column("source_secret", sa.Text(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("source_template", sa.Text(), nullable=False),
        sa.Column("llm_enabled", sa.Boolean(), nullable=False),
        sa.Column("llm_prompt", sa.Text(), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_template", sa.Text(), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("target_secret", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tb_webhooks_user_id", "tb_webhooks", ["user_id"])
    op.create_table(
        "tb_webhooks_log",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("wid", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("tb_user.id"), nullable=False),
        sa.Column("webhook_name", sa.String(100), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("delivery_id", sa.String(128)),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON()),
        sa.Column("llm_output", sa.Text()),
        sa.Column("config_snapshot", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("target_response", sa.JSON()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("output_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("cost_ms", sa.Integer()),
        sa.UniqueConstraint("wid", "delivery_id", name="uq_log_delivery"),
    )
    op.create_index("ix_tb_webhooks_log_wid", "tb_webhooks_log", ["wid"])
    op.create_index("ix_tb_webhooks_log_trace_id", "tb_webhooks_log", ["trace_id"])
    op.create_index("ix_log_queue", "tb_webhooks_log", ["status", "received_at"])
    op.create_index("ix_log_owner_time", "tb_webhooks_log", ["user_id", "received_at"])


def downgrade():
    op.drop_table("tb_webhooks_log")
    op.drop_table("tb_webhooks")
    op.drop_table("tb_user")
