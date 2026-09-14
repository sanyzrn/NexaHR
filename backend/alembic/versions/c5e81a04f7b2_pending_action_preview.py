"""جدولِ «چه چیزی عوض می‌شود» روی کنشِ در انتظارِ تأیید.

Revision ID: c5e81a04f7b2
Revises: a3f79c2b5d14
"""
import sqlalchemy as sa

from alembic import op

revision = "c5e81a04f7b2"
down_revision = "a3f79c2b5d14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ردیف‌های موجود خالی می‌مانند و کارتشان به همان جدولِ پیش‌فرضِ
    # آرگومان‌ها برمی‌گردد — بازساختنِ عکسِ *گذشته* ممکن نیست و ساختنِ یک
    # عکسِ امروزی برای تصمیمی که دیروز گرفته شده، دروغ است.
    op.add_column(
        "ai_pending_actions",
        sa.Column("preview_json", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("ai_pending_actions", "preview_json")
