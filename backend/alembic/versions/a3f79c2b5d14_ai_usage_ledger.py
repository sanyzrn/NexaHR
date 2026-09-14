"""دفترِ هزینهٔ دستیار: جدولِ فقط-افزودنیِ مصرفِ توکن.

Revision ID: a3f79c2b5d14
Revises: e6b4c1af90d2
"""
import sqlalchemy as sa

from alembic import op

revision = "a3f79c2b5d14"
down_revision = "e6b4c1af90d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        # `SET NULL` و نه `CASCADE`: هزینه اتفاق افتاده و حذفِ حساب آن را
        # برنمی‌گرداند. `username` عکسِ لحظه است تا ردیفِ بی‌صاحب هم خوانا بماند.
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("ai_conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_ai_usage_log_created_at", "ai_usage_log", ["created_at"])
    op.create_index(
        "ix_ai_usage_log_created_at_user", "ai_usage_log", ["created_at", "user_id"]
    )


def _refuse_if_the_ledger_has_entries(bind=None) -> None:
    """`downgrade` این جدول را می‌ریزد و دفتر با آن می‌رود.

    برخلافِ بیشترِ جدول‌های این سامانه، این یکی *بازساختنی نیست*: مصرفِ توکن
    را سرویسِ بیرونی گفته و هیچ‌جای دیگری در دیتابیس نیست. پیام‌های گفت‌وگو
    می‌مانند ولی هیچ‌کدام نمی‌گویند آن نوبت چند توکن سوزانده.

    یعنی یک رفت‌وبرگشتِ ساده، تنها سندِ داخلیِ سازمان برای مقابله با
    صورت‌حسابِ سرویس را پاک می‌کند — و آن‌هم بی‌صدا.
    """
    bind = bind or op.get_bind()
    rows = bind.execute(sa.text("SELECT count(*) FROM ai_usage_log")).scalar() or 0
    if rows:
        raise RuntimeError(
            f"downgrade متوقف شد: دفترِ هزینهٔ دستیار {rows} ردیف دارد و این "
            "داده جای دیگری در سامانه نیست — مصرفِ توکن را سرویسِ بیرونی گفته "
            "و با ریختنِ این جدول برای همیشه می‌رود. اگر واقعاً می‌خواهید، "
            "اول خروجی بگیرید: COPY ai_usage_log TO '/tmp/ai_usage.csv' CSV HEADER;"
        )


def downgrade() -> None:
    _refuse_if_the_ledger_has_entries()
    op.drop_index("ix_ai_usage_log_created_at_user", table_name="ai_usage_log")
    op.drop_index("ix_ai_usage_log_created_at", table_name="ai_usage_log")
    op.drop_table("ai_usage_log")
