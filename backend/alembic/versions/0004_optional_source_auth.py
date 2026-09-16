"""Per-rule optional source authentication; existing rules remain authenticated."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tb_webhooks",
        sa.Column("source_auth_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column("tb_webhooks", "source_auth_enabled")
