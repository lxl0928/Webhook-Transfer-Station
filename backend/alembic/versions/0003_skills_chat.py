"""User-owned skills and audited conversational tool execution."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tb_skill",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("tb_user.id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("builtin", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_skill_owner_name"),
    )
    op.create_index("ix_tb_skill_user_id", "tb_skill", ["user_id"])
    op.create_table(
        "tb_chat_conversation",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("tb_user.id"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("lease_token", sa.String(32)),
        sa.Column("busy_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tb_chat_conversation_user_id", "tb_chat_conversation", ["user_id"])
    op.create_table(
        "tb_chat_message",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(32),
            sa.ForeignKey("tb_chat_conversation.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_chat_message_order", "tb_chat_message", ["conversation_id", "created_at", "id"]
    )
    op.create_table(
        "tb_chat_action",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(32),
            sa.ForeignKey("tb_chat_conversation.id"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("arguments", sa.Text(), nullable=False),
        sa.Column("skill_ids", sa.JSON(), nullable=False),
        sa.Column("expected_state", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", sa.Text()),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_chat_action_pending", "tb_chat_action", ["conversation_id", "status"])


def downgrade():
    op.drop_table("tb_chat_action")
    op.drop_table("tb_chat_message")
    op.drop_table("tb_chat_conversation")
    op.drop_table("tb_skill")
