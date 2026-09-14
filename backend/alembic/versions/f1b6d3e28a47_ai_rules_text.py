"""آیین‌نامهٔ ارزیابی عملکردِ سازمان در تنظیمات دستیار.

Revision ID: f1b6d3e28a47
Revises: d8a2f61c39e5
"""
import sqlalchemy as sa

from alembic import op

revision = "f1b6d3e28a47"
down_revision = "d8a2f61c39e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # خالی شروع می‌شود و خالی‌بودنش بی‌ضرر است: پرامپت این بخش را فقط وقتی
    # اضافه می‌کند که متنی نوشته شده باشد. یعنی این مایگریشن هیچ رفتاری را
    # تا روزِ پرشدنِ فیلد عوض نمی‌کند.
    op.add_column(
        "ai_settings",
        sa.Column("rules_text", sa.Text(), nullable=False, server_default=""),
    )


def _refuse_if_the_rules_were_written(bind=None) -> None:
    """`downgrade` متنِ آیین‌نامه را می‌ریزد و جای دیگری از آن نسخه‌ای نیست.

    این ستون تنها جایی است که آیین‌نامه در سامانه زندگی می‌کند. فایلِ Wordِ
    اصلی ممکن است دستِ کسی باشد و ممکن است نباشد؛ سامانه نباید فرض کند.
    """
    bind = bind or op.get_bind()
    chars = (
        bind.execute(
            sa.text("SELECT coalesce(max(length(rules_text)), 0) FROM ai_settings")
        ).scalar()
        or 0
    )
    if chars:
        raise RuntimeError(
            f"downgrade متوقف شد: آیین‌نامهٔ سازمان نوشته شده ({chars} نویسه) و "
            "این ستون تنها جای نگهداری‌اش در سامانه است. اگر واقعاً می‌خواهید، "
            "اول یک نسخه بگیرید: "
            "COPY (SELECT rules_text FROM ai_settings) TO '/tmp/rules.txt';"
        )


def downgrade() -> None:
    _refuse_if_the_rules_were_written()
    op.drop_column("ai_settings", "rules_text")
