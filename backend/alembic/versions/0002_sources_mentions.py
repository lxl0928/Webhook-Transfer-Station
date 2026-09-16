"""Generic sources, configurable source authentication, and target mentions."""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tb_webhooks",
        sa.Column("source_auth", sa.String(16), nullable=False, server_default="header"),
    )
    op.add_column(
        "tb_webhooks",
        sa.Column(
            "source_token_header", sa.String(64), nullable=False, server_default="X-Webhook-Token"
        ),
    )
    op.add_column(
        "tb_webhooks", sa.Column("target_mentions", sa.JSON(), nullable=False, server_default="{}")
    )


def downgrade():
    op.drop_column("tb_webhooks", "target_mentions")
    op.drop_column("tb_webhooks", "source_token_header")
    op.drop_column("tb_webhooks", "source_auth")
