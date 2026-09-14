"""خلاصهٔ غلتانِ گفت‌وگو.

Revision ID: d8a2f61c39e5
Revises: c5e81a04f7b2
"""
import sqlalchemy as sa

from alembic import op

revision = "d8a2f61c39e5"
down_revision = "c5e81a04f7b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_conversations",
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
    )
    # صفر یعنی «هنوز هیچ پیامی خلاصه نشده» — پس گفت‌وگوهای موجود از همان
    # نوبتِ بعدی‌شان شروع به جمع‌بندی می‌کنند و چیزی بازسازی نمی‌شود.
    op.add_column(
        "ai_conversations",
        sa.Column(
            "summary_through_message_id", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_conversations", "summary_through_message_id")
    op.drop_column("ai_conversations", "summary_text")
